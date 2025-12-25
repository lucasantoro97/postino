from __future__ import annotations

from agent.llm_openrouter import HeuristicLlm, OpenRouterConfig, OpenRouterLlm
from agent.models import EmailMeta


def test_heuristic_reply_italian() -> None:
    llm = HeuristicLlm()
    meta = EmailMeta(folder="INBOX", uid=1, subject="Richiesta")
    draft = llm.draft_reply(meta=meta, text="Grazie per la tua email.")
    assert "Grazie" in draft.body


def test_heuristic_reply_english() -> None:
    llm = HeuristicLlm()
    meta = EmailMeta(folder="INBOX", uid=1, subject="Request")
    draft = llm.draft_reply(meta=meta, text="Thanks for your email.")
    assert "Thanks for your email" in draft.body


def test_openrouter_prompt_uses_language(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, str] = {}

    def fake_chat_text(self, *, system: str, user: str):  # type: ignore[no-untyped-def,unused-argument]
        captured["system"] = system
        return "ok"

    monkeypatch.setattr(OpenRouterLlm, "_chat_text", fake_chat_text)
    llm = OpenRouterLlm(OpenRouterConfig(api_key="k", model="m", base_url="http://x"))
    meta = EmailMeta(folder="INBOX", uid=1, subject="Richiesta", from_addr="a@example.com")
    llm.draft_reply(meta=meta, text="Grazie per la tua email.")
    assert "Italian" in captured["system"]
