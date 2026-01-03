from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Protocol

from openai import OpenAI
from pydantic import ValidationError

from .models import (
    ActionPlan,
    ClassificationCategory,
    ClassificationResult,
    EmailMeta,
    EventCandidate,
    ReplyDraft,
)

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[a-zA-ZÀ-ÿ']+")
_ITALIAN_STOPWORDS = {
    "e",
    "il",
    "lo",
    "la",
    "i",
    "gli",
    "le",
    "un",
    "una",
    "di",
    "da",
    "che",
    "per",
    "con",
    "su",
    "come",
    "mi",
    "ti",
    "si",
    "sono",
    "grazie",
    "buongiorno",
    "cordiali",
    "saluti",
}
_ENGLISH_STOPWORDS = {
    "and",
    "the",
    "a",
    "an",
    "of",
    "to",
    "for",
    "with",
    "on",
    "in",
    "is",
    "are",
    "thank",
    "hello",
    "regards",
}


class LlmClient(Protocol):
    def classify(self, *, meta: EmailMeta, text: str) -> ClassificationResult: ...

    def draft_reply(self, *, meta: EmailMeta, text: str) -> ReplyDraft: ...

    def extract_events(self, *, meta: EmailMeta, text: str) -> list[EventCandidate]: ...


@dataclass(frozen=True)
class OpenRouterConfig:
    api_key: str
    model: str
    base_url: str


class OpenRouterLlm(LlmClient):
    def __init__(self, cfg: OpenRouterConfig) -> None:
        self._client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)
        self._model = cfg.model

    def _chat(self, *, system: str, user: str, response_format: dict | None = None) -> str:
        payload = {
            "model": self._model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if response_format is not None:
            payload["response_format"] = response_format
        try:
            resp = self._client.chat.completions.create(**payload)
        except Exception as exc:
            if response_format is None:
                raise
            logger.warning(
                "JSON mode failed; retrying without response_format",
                extra={"extra": {"error": str(exc)}},
            )
            payload.pop("response_format", None)
            resp = self._client.chat.completions.create(**payload)
        return (resp.choices[0].message.content or "").strip()

    def _chat_text(self, *, system: str, user: str) -> str:
        return self._chat(system=system, user=user)

    def _chat_json_value(self, *, system: str, user: str, expected: str) -> object:
        response_format = {"type": "json_object"} if expected == "object" else None
        content = self._chat(system=system, user=user, response_format=response_format)
        # Handle cases where LLM wraps JSON in markdown code blocks
        if content.startswith("```"):
            # Find the first { or [ after the first ```
            # or just strip the backticks and any language identifier
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            repaired = self._repair_json(text=content, expected=expected)
            repaired = repaired.strip()
            if repaired.startswith("```"):
                lines = repaired.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                repaired = "\n".join(lines).strip()
            try:
                parsed = json.loads(repaired)
            except json.JSONDecodeError as repair_error:
                raise RuntimeError(f"LLM did not return JSON: {content[:500]}") from repair_error
        return parsed

    def _repair_json(self, *, text: str, expected: str) -> str:
        if expected == "list":
            system = (
                "You are a strict JSON formatter. Convert the input to a JSON array only. "
                "If the input says there are no items, return []."
            )
        else:
            system = (
                "You are a strict JSON formatter. Convert the input to a JSON object only. "
                "Do not include markdown or extra text."
            )
        user = f"Input:\n{text}\n\nReturn only JSON."
        return self._chat_text(system=system, user=user)

    def _chat_json(self, *, system: str, user: str) -> dict:
        parsed = self._chat_json_value(system=system, user=user, expected="object")
        if not isinstance(parsed, dict):
            raise RuntimeError(f"LLM did not return a JSON object: {str(parsed)[:500]}")
        return parsed

    def _chat_json_list(self, *, system: str, user: str) -> list:
        parsed = self._chat_json_value(system=system, user=user, expected="list")
        if isinstance(parsed, list):
            return parsed
        # Some models occasionally return a single object instead of a singleton list.
        # This is especially common when the prompt asks for an "array" but the model
        # decides it found exactly one item.
        if isinstance(parsed, dict) and {"summary", "start"}.issubset(parsed.keys()):
            return [parsed]
        raise RuntimeError(f"LLM did not return a JSON list: {str(parsed)[:500]}")

    def classify(self, *, meta: EmailMeta, text: str) -> ClassificationResult:
        system = (
            "You classify emails into one of: "
            "ToReply, Receipts, Newsletters, Notifications, "
            "CalendarCreated, NoAction, NeedsReview. "
            "Set contains_event_request=true when the email includes a meeting time "
            "or an explicit deadline (e.g., 'by Friday', 'entro il 12/01'). "
            "Return ONLY valid JSON matching the schema."
        )
        schema_hint = {
            "category": "ToReply",
            "confidence": 0.0,
            "rationale": "string",
            "tags": ["string"],
            "reply_needed": False,
            "contains_event_request": False,
        }
        user = (
            f"Email meta:\n{meta.model_dump_json(exclude_none=True)}\n\n"
            f"Email text:\n{text[:8000]}\n\n"
            f"Return JSON like:\n{json.dumps(schema_hint)}"
        )
        raw = self._chat_json(system=system, user=user)
        try:
            return ClassificationResult.model_validate(raw)
        except ValidationError as e:
            raise RuntimeError(f"LLM classification schema error: {raw}") from e

    def draft_reply(self, *, meta: EmailMeta, text: str) -> ReplyDraft:
        language = _detect_language(text, meta.subject or "")
        language_hint = "Italian" if language == "it" else "English"
        system = (
            f"You draft concise professional email replies in {language_hint}. "
            "Never promise actions you cannot verify. "
            "Return only the email body as plain text without JSON or markdown."
        )
        context_lines = [
            f"From: {meta.from_addr}" if meta.from_addr else "",
            f"To: {meta.to_addr}" if meta.to_addr else "",
            f"Cc: {meta.cc_addr}" if meta.cc_addr else "",
            f"Date: {meta.date}" if meta.date else "",
            f"In-Reply-To: {meta.in_reply_to}" if meta.in_reply_to else "",
            f"References: {' '.join(meta.references)}" if meta.references else "",
        ]
        context_block = "\n".join(line for line in context_lines if line)
        to_addr = meta.reply_to or meta.from_addr or ""
        subj = meta.subject or ""
        user = (
            f"Original email subject: {subj}\n"
            f"Original sender: {meta.from_addr}\n"
            f"Reply recipient: {to_addr}\n\n"
            f"Thread context:\n{context_block}\n\n"
            f"Email text:\n{text[:8000]}\n\n"
            "Return only the reply body text."
        )
        body = self._chat_text(system=system, user=user).strip()
        if not body:
            if language == "it":
                body = "Grazie per la tua email.\n\nCordiali saluti,\n"
            else:
                body = "Thanks for your email.\n\nBest regards,\n"
        return ReplyDraft(
            to_addr=to_addr,
            subject=_normalize_reply_subject(subj),
            body=body,
            in_reply_to=meta.message_id,
            references=_normalize_references(meta.references, meta.message_id),
        )

    def extract_events(self, *, meta: EmailMeta, text: str) -> list[EventCandidate]:
        system = (
            "Extract calendar events and deadline-based TODOs from emails. "
            "Create events for meetings or explicit scheduling requests. "
            "For tasks with a deadline (e.g., 'by Friday', 'entro il 12/01'), "
            "create a short TODO event at the deadline time and prefix the summary with 'TODO:'. "
            "If you see a video-call / meeting URL (e.g. meet.google.com, zoom.us, "
            "teams.microsoft.com, webex), "
            "put it in the 'location' field and also include it in 'evidence'. "
            "Return ONLY valid JSON: an array of event candidates. "
            "Do not invent dates or times; only extract if present."
        )
        schema_hint = [
            {
                "summary": "string",
                "start": "ISO or natural language datetime",
                "end": "ISO or natural language datetime or null",
                "duration_minutes": 30,
                "timezone": "IANA tz or null",
                "location": "string or null",
                "evidence": ["short quote"],
            }
        ]
        user = (
            f"Email meta:\n{meta.model_dump_json(exclude_none=True)}\n\n"
            f"Email text:\n{text[:12000]}\n\n"
            f"Return JSON like:\n{json.dumps(schema_hint)}"
        )
        raw = self._chat_json_list(system=system, user=user)
        out: list[EventCandidate] = []
        for item in raw:
            try:
                out.append(EventCandidate.model_validate(item))
            except ValidationError:
                logger.info("Skipping invalid event candidate", extra={"extra": {"item": item}})
        return out


class HeuristicLlm(LlmClient):
    def classify(self, *, meta: EmailMeta, text: str) -> ClassificationResult:
        subj = (meta.subject or "").lower()
        body = text.lower()
        if "unsubscribe" in body or "newsletter" in subj:
            return ClassificationResult(
                category=ClassificationCategory.Newsletters,
                confidence=0.7,
                rationale="Heuristic: newsletter/unsubscribe",
                tags=["heuristic"],
                reply_needed=False,
                contains_event_request=False,
            )
        if any(k in body for k in ("invoice", "receipt", "payment")):
            return ClassificationResult(
                category=ClassificationCategory.Receipts,
                confidence=0.7,
                rationale="Heuristic: invoice/receipt keywords",
                tags=["heuristic"],
                reply_needed=False,
                contains_event_request=False,
            )
        if "meeting" in body or "calendar" in body:
            return ClassificationResult(
                category=ClassificationCategory.ToReply,
                confidence=0.55,
                rationale="Heuristic: meeting/calendar keywords",
                tags=["heuristic"],
                reply_needed=True,
                contains_event_request=True,
            )
        return ClassificationResult(
            category=ClassificationCategory.NeedsReview,
            confidence=0.5,
            rationale="Heuristic fallback",
            tags=["heuristic"],
            reply_needed=False,
            contains_event_request=False,
        )

    def draft_reply(self, *, meta: EmailMeta, text: str) -> ReplyDraft:
        language = _detect_language(text, meta.subject or "")
        to_addr = meta.reply_to or meta.from_addr or ""
        subject = _normalize_reply_subject(meta.subject or "")
        if language == "it":
            body = (
                "Grazie per la tua email.\n\n"
                "Ho ricevuto il tuo messaggio e lo esaminerò a breve.\n\n"
                "Cordiali saluti,\n"
            )
        else:
            body = (
                "Thanks for your email.\n\n"
                "I’ve received your message and will review it shortly.\n\n"
                "Best regards,\n"
            )
        return ReplyDraft(
            to_addr=to_addr,
            subject=subject,
            body=body,
            in_reply_to=meta.message_id,
            references=_normalize_references(meta.references, meta.message_id),
        )

    def extract_events(self, *, meta: EmailMeta, text: str) -> list[EventCandidate]:
        return []


def decide_actions(classification: ClassificationResult) -> ActionPlan:
    return ActionPlan(
        create_draft=classification.reply_needed,
        extract_event=classification.contains_event_request,
        create_calendar_event=classification.contains_event_request,
        file_email=True,
    )


def _normalize_reply_subject(subject: str) -> str:
    s = subject.strip()
    if s.lower().startswith("re:"):
        return s
    return f"Re: {s}" if s else "Re:"


def _normalize_references(references: list[str], message_id: str | None) -> str | None:
    ordered: list[str] = []
    seen: set[str] = set()
    for ref in references:
        key = ref.strip()
        if not key or key in seen:
            continue
        ordered.append(key)
        seen.add(key)
    if message_id:
        key = message_id.strip()
        if key and key not in seen:
            ordered.append(key)
    return " ".join(ordered) if ordered else None


def _detect_language(*parts: str) -> str:
    text = " ".join(p for p in parts if p).lower()
    words = _WORD_RE.findall(text)
    if not words:
        return "en"
    it_score = sum(1 for w in words if w in _ITALIAN_STOPWORDS)
    en_score = sum(1 for w in words if w in _ENGLISH_STOPWORDS)
    if it_score == 0 and en_score == 0:
        return "en"
    return "it" if it_score >= en_score else "en"
