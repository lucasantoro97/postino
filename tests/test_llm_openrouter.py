from unittest.mock import MagicMock

import pytest

from agent.llm_openrouter import OpenRouterConfig, OpenRouterLlm


@pytest.fixture
def mock_cfg():
    return OpenRouterConfig(api_key="fake", model="fake", base_url="fake")


def test_chat_json_handles_markdown(mock_cfg):
    llm = OpenRouterLlm(mock_cfg)
    llm._client = MagicMock()

    # Mock response with markdown-wrapped JSON
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="```json\n{\"key\": \"value\"}\n```"))]
    llm._client.chat.completions.create.return_value = mock_resp

    result = llm._chat_json(system="sys", user="user")
    assert result == {"key": "value"}


def test_chat_json_handles_raw_json(mock_cfg):
    llm = OpenRouterLlm(mock_cfg)
    llm._client = MagicMock()

    # Mock response with raw JSON
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="{\"key\": \"value\"}"))]
    llm._client.chat.completions.create.return_value = mock_resp

    result = llm._chat_json(system="sys", user="user")
    assert result == {"key": "value"}


def test_chat_json_handles_markdown_list(mock_cfg):
    llm = OpenRouterLlm(mock_cfg)
    llm._client = MagicMock()

    # Mock response with markdown-wrapped JSON list
    mock_resp = MagicMock()
    mock_resp.choices = [
        MagicMock(message=MagicMock(content="```json\n[{\"key\": \"value\"}]\n```"))
    ]
    llm._client.chat.completions.create.return_value = mock_resp

    result = llm._chat_json_list(system="sys", user="user")
    assert result == [{"key": "value"}]


def test_chat_json_list_wraps_single_object(mock_cfg):
    llm = OpenRouterLlm(mock_cfg)
    llm._client = MagicMock()

    mock_resp = MagicMock()
    mock_resp.choices = [
        MagicMock(
            message=MagicMock(
                content='{"summary":"Sync","start":"2025-01-10 10:00","end":null,"timezone":"UTC"}'
            )
        )
    ]
    llm._client.chat.completions.create.return_value = mock_resp

    result = llm._chat_json_list(system="sys", user="user")
    assert result == [
        {"summary": "Sync", "start": "2025-01-10 10:00", "end": None, "timezone": "UTC"}
    ]


def test_chat_json_raises_on_invalid_json(mock_cfg):
    llm = OpenRouterLlm(mock_cfg)
    llm._client = MagicMock()

    # Mock response with invalid JSON
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="invalid json"))]
    llm._client.chat.completions.create.return_value = mock_resp

    with pytest.raises(RuntimeError, match="LLM did not return JSON"):
        llm._chat_json(system="sys", user="user")


def test_extract_events_returns_empty_on_non_json_model_reply(mock_cfg, monkeypatch):
    llm = OpenRouterLlm(mock_cfg)

    def fake_chat_json(*, system, user):  # type: ignore[no-untyped-def]
        raise RuntimeError("LLM did not return JSON: plain text")

    monkeypatch.setattr(OpenRouterLlm, "_chat_json", staticmethod(fake_chat_json))

    meta = MagicMock()
    meta.uid = 123
    meta.model_dump_json.return_value = "{}"

    assert llm.extract_events(meta=meta, text="hello") == []
