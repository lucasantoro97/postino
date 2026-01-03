from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import Settings
from .deps import Deps
from .email_parse import parse_email
from .executive_brief import build_executive_brief, should_run_executive_brief
from .google_calendar import CalendarConfig, GoogleCalendarClient
from .graph import build_email_graph
from .imap_client import ImapClient, ImapMessageNotFound
from .llm_openrouter import HeuristicLlm, LlmClient, OpenRouterConfig, OpenRouterLlm
from .logging import configure_logging
from .recaps import (
    build_daily_recap,
    build_replied_digest,
    build_weekly_recap,
    should_run_daily,
    should_run_weekly,
)
from .rfc822 import build_executive_brief_email
from .state_store import StateStore

logger = logging.getLogger(__name__)
_ANSWERED_FLAG = "answered"


def _has_answered_flag(flags: set[str]) -> bool:
    for flag in flags:
        normalized = flag.strip().lstrip("\\").lower()
        if normalized == _ANSWERED_FLAG:
            return True
    return False


def initial_backfill_uids(*, deps: Deps, inbox: str, lookback_days: int) -> list[int]:
    since_date = (datetime.now(tz=timezone.utc) - timedelta(days=lookback_days)).date()
    uids = deps.imap.uid_search_since_date(since_date)
    all_uids = deps.imap.uid_search_all()
    if all_uids:
        deps.store.set_last_uid(inbox, max(all_uids))
    return uids


def _build_llm(settings: Settings) -> LlmClient:
    if settings.openrouter_api_key and settings.openrouter_model:
        return OpenRouterLlm(
            OpenRouterConfig(
                api_key=settings.openrouter_api_key,
                model=settings.openrouter_model,
                base_url=settings.openrouter_base_url,
            )
        )
    return HeuristicLlm()


def _build_calendar(settings: Settings) -> GoogleCalendarClient | None:
    if not settings.google_token_path.exists():
        return None
    return GoogleCalendarClient(
        CalendarConfig(
            token_path=settings.google_token_path,
            calendar_id=settings.google_calendar_id,
        )
    )


def ensure_folders(*, settings: Settings, imap: ImapClient) -> None:
    for folder in settings.all_required_folders:
        try:
            imap.ensure_mailbox(folder)
        except Exception:
            logger.exception(
                "Failed ensuring mailbox",
                extra={"event": "ensure_mailbox_failed", "extra": {"mailbox": folder}},
            )


def process_one_uid(*, deps: Deps, graph, uid: int) -> None:  # type: ignore[no-untyped-def]
    settings = deps.settings
    deps.imap.select(settings.imap_folder_inbox, readonly=False)
    flags = deps.imap.fetch_flags(uid)
    try:
        raw = deps.imap.fetch_rfc822(uid)
    except ImapMessageNotFound:
        # The message may have been expunged/moved between SEARCH and FETCH, or it may be a stale
        # retry entry in the state DB. Treat as non-fatal and stop retry churn.
        logger.info(
            "Email missing on fetch, skipping",
            extra={
                "event": "email_missing",
                "email_uid": uid,
                "email_folder": settings.imap_folder_inbox,
            },
        )
        deps.store.set_filing_result(
            settings.imap_folder_inbox,
            uid,
            filing_folder=settings.imap_folder_inbox,
            status="moved",
        )
        return
    meta, text, fingerprint = parse_email(raw, folder=settings.imap_folder_inbox, uid=uid)
    logger.info(
        "Email fetched",
        extra={
            "event": "email_fetched",
            "email_uid": meta.uid,
            "email_folder": meta.folder,
            "imap_fetch": "body_peek",
        },
    )

    deps.store.upsert_message_base(
        folder=meta.folder,
        uid=meta.uid,
        message_id=meta.message_id,
        subject=meta.subject,
        from_addr=meta.from_addr,
        date=meta.date,
        fingerprint=fingerprint,
    )
    if settings.imap_skip_answered and _has_answered_flag(flags):
        logger.info(
            "Skipping answered email",
            extra={
                "event": "email_skipped_answered",
                "email_uid": meta.uid,
                "email_folder": meta.folder,
                "extra": {"flags": sorted(flags)},
            },
        )
        deps.store.set_filing_result(
            meta.folder,
            meta.uid,
            filing_folder=meta.folder,
            status="skipped",
        )
        return

    state = {"meta": meta, "text": text, "fingerprint": fingerprint}
    try:
        out = graph.invoke(state)
        classification = out["classification"]
        deps.store.set_classification(
            folder=meta.folder,
            uid=meta.uid,
            category=classification.category,
            confidence=classification.confidence,
            rationale=classification.rationale,
            tags_json=out.get("classification_tags_json", "[]"),
            reply_needed=classification.reply_needed,
            contains_event_request=classification.contains_event_request,
            priority=int(out.get("priority") or 0),
        )
    except Exception as e:
        deps.store.record_attempt(meta.folder, meta.uid, error=str(e))
        raise


def maybe_run_executive_brief(*, deps: Deps) -> None:
    settings = deps.settings
    if not settings.executive_brief_enabled:
        return
    ok, local_date = should_run_executive_brief(
        now_utc=datetime.now(tz=timezone.utc),
        tz=settings.tz,
        time_local_hhmm=settings.executive_brief_time_local,
    )
    if not ok:
        return
    if deps.store.executive_brief_exists(local_date=local_date):
        return

    to_addr = settings.executive_brief_to or settings.imap_username
    brief = build_executive_brief(
        store=deps.store,
        now_local=datetime.now(tz=timezone.utc).astimezone(ZoneInfo(settings.tz)),
        lookback_hours=settings.executive_brief_lookback_hours,
        subject_prefix=settings.executive_brief_subject_prefix,
    )
    msg = build_executive_brief_email(
        from_addr=settings.imap_username, to_addr=to_addr, subject=brief.subject, body=brief.body
    )
    deps.imap.select(settings.imap_drafts_folder, readonly=False)
    res = deps.imap.append(settings.imap_drafts_folder, msg, flags=("\\Draft",))
    if not res.ok:
        raise RuntimeError(f"IMAP APPEND for executive brief failed: {res.raw_response!r}")
    deps.store.record_executive_brief(local_date=local_date, draft_uid=res.appended_uid)
    logger.info("Executive brief drafted", extra={"event": "executive_brief_drafted"})


def _send_recap_message(
    *,
    deps: Deps,
    subject: str,
    body: str,
    to_addr: str,
) -> int | None:
    settings = deps.settings
    if not settings.imap_sent_folder:
        raise RuntimeError("IMAP_SENT_FOLDER is required to send recaps")
    msg = build_executive_brief_email(
        from_addr=settings.imap_username,
        to_addr=to_addr,
        subject=subject,
        body=body,
    )
    deps.imap.select(settings.imap_sent_folder, readonly=False)
    res = deps.imap.append(settings.imap_sent_folder, msg, flags=("\\Seen",))
    if not res.ok:
        raise RuntimeError(f"IMAP APPEND for recap failed: {res.raw_response!r}")
    return res.appended_uid


def maybe_run_daily_recap(*, deps: Deps) -> None:
    settings = deps.settings
    if not settings.daily_recap_enabled:
        return
    ok, local_date = should_run_daily(
        now_utc=datetime.now(tz=timezone.utc),
        tz=settings.tz,
        time_local_hhmm=settings.daily_recap_time_local,
    )
    if not ok:
        return
    if deps.store.daily_recap_exists(local_date=local_date):
        return
    recap = build_daily_recap(
        store=deps.store,
        now_local=datetime.now(tz=timezone.utc).astimezone(ZoneInfo(settings.tz)),
        lookback_hours=settings.daily_recap_lookback_hours,
        subject_prefix=settings.daily_recap_subject_prefix,
    )
    to_addr = settings.daily_recap_to or settings.imap_username
    sent_uid = _send_recap_message(
        deps=deps, subject=recap.subject, body=recap.body, to_addr=to_addr
    )
    deps.store.record_daily_recap(local_date=local_date, draft_uid=sent_uid)
    logger.info("Daily recap sent", extra={"event": "daily_recap_sent"})


def maybe_run_weekly_recap(*, deps: Deps) -> None:
    settings = deps.settings
    if not settings.weekly_recap_enabled:
        return
    ok, week_key = should_run_weekly(
        now_utc=datetime.now(tz=timezone.utc),
        tz=settings.tz,
        time_local_hhmm=settings.weekly_recap_time_local,
        day_local=settings.weekly_recap_day_local,
    )
    if not ok:
        return
    if deps.store.weekly_recap_exists(week_key=week_key):
        return
    recap = build_weekly_recap(
        store=deps.store,
        now_local=datetime.now(tz=timezone.utc).astimezone(ZoneInfo(settings.tz)),
        lookback_days=settings.weekly_recap_lookback_days,
        subject_prefix=settings.weekly_recap_subject_prefix,
    )
    to_addr = settings.weekly_recap_to or settings.imap_username
    sent_uid = _send_recap_message(
        deps=deps, subject=recap.subject, body=recap.body, to_addr=to_addr
    )
    deps.store.record_weekly_recap(week_key=week_key, draft_uid=sent_uid)
    logger.info("Weekly recap sent", extra={"event": "weekly_recap_sent"})


def maybe_run_replied_digest(*, deps: Deps) -> None:
    settings = deps.settings
    if not settings.replied_digest_enabled:
        return
    ok, local_date = should_run_daily(
        now_utc=datetime.now(tz=timezone.utc),
        tz=settings.tz,
        time_local_hhmm=settings.replied_digest_time_local,
    )
    if not ok:
        return
    if deps.store.replied_digest_exists(local_date=local_date):
        return
    digest = build_replied_digest(
        store=deps.store,
        now_local=datetime.now(tz=timezone.utc).astimezone(ZoneInfo(settings.tz)),
        subject_prefix=settings.replied_digest_subject_prefix,
    )
    to_addr = settings.replied_digest_to or settings.imap_username
    sent_uid = _send_recap_message(
        deps=deps, subject=digest.subject, body=digest.body, to_addr=to_addr
    )
    deps.store.record_replied_digest(local_date=local_date, draft_uid=sent_uid)
    logger.info("Reply digest sent", extra={"event": "reply_digest_sent"})


def reconcile_replied_messages(*, deps: Deps) -> None:
    settings = deps.settings
    if not settings.imap_sent_folder:
        return
    to_reply_folder = settings.classification_folders.get("ToReply", "ToReply")
    replied_folder = settings.imap_replied_folder or "NoAction"
    candidates = deps.store.reply_candidates(filing_folder=to_reply_folder)
    if not candidates:
        return
    try:
        with deps.imap.temporary_select(settings.imap_sent_folder, readonly=True):
            replied_message_ids: set[str] = set()
            for candidate in candidates:
                message_id = candidate.message_id
                if not message_id or message_id in replied_message_ids:
                    continue
                in_reply = deps.imap.uid_search_header("In-Reply-To", message_id)
                refs = deps.imap.uid_search_header("References", message_id)
                if in_reply or refs:
                    replied_message_ids.add(message_id)
    except Exception:
        logger.exception(
            "Failed scanning sent folder",
            extra={"event": "sent_scan_failed", "email_folder": settings.imap_sent_folder},
        )
        return

    if not replied_message_ids:
        return
    if settings.imap_create_folders_on_startup:
        deps.imap.ensure_mailbox(replied_folder)
    with deps.imap.temporary_select(to_reply_folder, readonly=False):
        for candidate in candidates:
            message_id = candidate.message_id
            if not message_id or message_id not in replied_message_ids:
                continue
            try:
                uids = deps.imap.uid_search_header("Message-ID", message_id)
                if not uids:
                    logger.info(
                        "Replied message not found in folder",
                        extra={
                            "event": "replied_message_missing",
                            "email_message_id": message_id,
                            "email_folder": to_reply_folder,
                        },
                    )
                    continue
                deps.imap.move(uids[0], dest_mailbox=replied_folder)
                deps.store.mark_replied(
                    candidate.folder, candidate.uid, replied_folder=replied_folder
                )
                local_date = (
                    datetime.now(tz=timezone.utc)
                    .astimezone(ZoneInfo(settings.tz))
                    .strftime("%Y-%m-%d")
                )
                deps.store.record_replied_move(
                    local_date=local_date,
                    message_id=message_id,
                    subject=candidate.subject,
                    from_addr=candidate.from_addr,
                )
                logger.info(
                    "Moved replied email out of ToReply",
                    extra={
                        "event": "replied_email_moved",
                        "email_message_id": message_id,
                        "email_folder": to_reply_folder,
                        "dest_folder": replied_folder,
                    },
                )
            except Exception:
                logger.exception(
                    "Failed moving replied email",
                    extra={
                        "event": "replied_email_move_failed",
                        "email_message_id": message_id,
                        "email_folder": to_reply_folder,
                        "dest_folder": replied_folder,
                    },
                )


def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    settings.agent_data_dir.mkdir(parents=True, exist_ok=True)
    debug_loggers = None
    if settings.parser_debug:
        debug_loggers = ("agent.email_parse", "agent.nodes.decide_actions")
    configure_logging(settings.log_level, debug_loggers=debug_loggers)

    store = StateStore(settings.database_path)
    llm = _build_llm(settings)
    calendar = _build_calendar(settings)

    backoff_seconds = 5
    while True:
        try:
            with ImapClient(
                host=settings.imap_host,
                port=settings.imap_port,
                username=settings.imap_username,
                password=settings.imap_password,
                mailbox_prefix=settings.imap_mailbox_prefix,
            ) as imap:
                backoff_seconds = 5
                if settings.imap_create_folders_on_startup:
                    ensure_folders(settings=settings, imap=imap)
                deps = Deps(settings=settings, store=store, imap=imap, llm=llm, calendar=calendar)
                graph = build_email_graph(deps)

                inbox = settings.imap_folder_inbox
                last_reconcile = 0.0
                while True:
                    try:
                        maybe_run_executive_brief(deps=deps)
                        maybe_run_daily_recap(deps=deps)
                        maybe_run_weekly_recap(deps=deps)
                        maybe_run_replied_digest(deps=deps)
                        if time.time() - last_reconcile >= settings.poll_seconds:
                            reconcile_replied_messages(deps=deps)
                            last_reconcile = time.time()

                        imap.select(inbox, readonly=False)
                        last_uid = store.get_last_uid(inbox)
                        if last_uid == 0:
                            uids = initial_backfill_uids(
                                deps=deps,
                                inbox=inbox,
                                lookback_days=settings.imap_initial_lookback_days,
                            )
                            for uid in uids:
                                try:
                                    process_one_uid(deps=deps, graph=graph, uid=uid)
                                except Exception:
                                    logger.exception(
                                        "Failed processing email",
                                        extra={
                                            "event": "process_failed",
                                            "email_uid": uid,
                                            "email_folder": inbox,
                                        },
                                    )
                            time.sleep(settings.poll_seconds)
                            continue

                        uids = imap.uid_search_since(last_uid)
                        if uids:
                            store.set_last_uid(inbox, max(uids))
                        for uid in uids:
                            try:
                                process_one_uid(deps=deps, graph=graph, uid=uid)
                            except Exception:
                                logger.exception(
                                    "Failed processing email",
                                    extra={
                                        "event": "process_failed",
                                        "email_uid": uid,
                                        "email_folder": inbox,
                                    },
                                )
                        retry_uids = store.retryable_uids(
                            inbox,
                            min_age_seconds=max(30, settings.poll_seconds),
                            limit=20,
                        )
                        for uid in retry_uids:
                            if uid in uids:
                                continue
                            try:
                                process_one_uid(deps=deps, graph=graph, uid=uid)
                            except Exception:
                                logger.exception(
                                    "Failed retrying email",
                                    extra={
                                        "event": "retry_failed",
                                        "email_uid": uid,
                                        "email_folder": inbox,
                                    },
                                )
                        time.sleep(settings.poll_seconds)
                    except Exception:
                        logger.exception("Poll loop error", extra={"event": "poll_loop_error"})
                        time.sleep(min(settings.poll_seconds, 30))
        except Exception:
            logger.exception(
                "IMAP connection error",
                extra={
                    "event": "imap_connect_error",
                    "extra": {"host": settings.imap_host, "port": settings.imap_port},
                },
            )
            time.sleep(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 2, 60)


if __name__ == "__main__":
    main()
