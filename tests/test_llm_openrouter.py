from unittest.mock import MagicMock

import pytest

from src.agent.llm_openrouter import OpenRouterConfig, OpenRouterLlm


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


def test_chat_json_raises_on_invalid_json(mock_cfg):
    llm = OpenRouterLlm(mock_cfg)
    llm._client = MagicMock()

    # Mock response with invalid JSON
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="invalid json"))]
    llm._client.chat.completions.create.return_value = mock_resp

    with pytest.raises(RuntimeError, match="LLM did not return JSON"):
        llm._chat_json(system="sys", user="user")
