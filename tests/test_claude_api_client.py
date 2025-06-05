import os
import types
from unittest.mock import MagicMock

from gmail_chatbot.email_claude_api import ClaudeAPIClient, CLAUDE_API_KEY_ENV


def test_process_email_content_model_forwarded(monkeypatch):
    os.environ[CLAUDE_API_KEY_ENV] = "test-key"
    mock_response = MagicMock()
    mock_response.content = [types.SimpleNamespace(text="ok")]
    mock_response.usage = types.SimpleNamespace(
        input_tokens=1, output_tokens=1
    )
    create_mock = MagicMock(return_value=mock_response)
    mock_client = MagicMock()
    mock_client.messages.create = create_mock
    monkeypatch.setattr(
        "anthropic.Anthropic", lambda api_key: mock_client, raising=False
    )

    client = ClaudeAPIClient(model="dummy", prep_model="prep-model")
    email_data = {"id": "1"}
    client.process_email_content(
        email_data, "summary", "sys", model=client.prep_model
    )

    create_mock.assert_called_once()
    assert create_mock.call_args.kwargs["model"] == client.prep_model


def test_process_query_model_not_found(monkeypatch):
    os.environ[CLAUDE_API_KEY_ENV] = "test-key"

    class NotFoundError(Exception):
        pass

    monkeypatch.setattr(
        "anthropic.errors",
        types.SimpleNamespace(NotFoundError=NotFoundError),
        raising=False,
    )
    monkeypatch.setattr("anthropic.APIError", NotFoundError, raising=False)

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = NotFoundError("bad model")
    monkeypatch.setattr(
        "anthropic.Anthropic", lambda api_key: mock_client, raising=False
    )

    client = ClaudeAPIClient(model="bad", prep_model="prep-model")
    result = client.process_query("query", "sys")
    assert "invalid or inaccessible" in result.lower()


def test_process_email_content_model_not_found(monkeypatch):
    os.environ[CLAUDE_API_KEY_ENV] = "test-key"

    class NotFoundError(Exception):
        pass

    monkeypatch.setattr(
        "anthropic.errors",
        types.SimpleNamespace(NotFoundError=NotFoundError),
        raising=False,
    )
    monkeypatch.setattr("anthropic.APIError", NotFoundError, raising=False)

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = NotFoundError("bad model")
    monkeypatch.setattr(
        "anthropic.Anthropic", lambda api_key: mock_client, raising=False
    )

    client = ClaudeAPIClient(model="bad", prep_model="prep-model")
    result = client.process_email_content({"id": "1"}, "sum", "sys")
    assert "invalid or inaccessible" in result.lower()


def test_summarize_triage_uses_triage_model(monkeypatch):
    os.environ[CLAUDE_API_KEY_ENV] = "test-key"
    mock_response = MagicMock()
    mock_response.content = [types.SimpleNamespace(text="summary")]
    mock_response.usage = types.SimpleNamespace(input_tokens=1, output_tokens=1)
    create_mock = MagicMock(return_value=mock_response)
    mock_client = MagicMock()
    mock_client.messages.create = create_mock
    monkeypatch.setattr(
        "anthropic.Anthropic", lambda api_key: mock_client, raising=False
    )

    client = ClaudeAPIClient(triage_model="triage-model")
    client.summarize_triage([], [], "req")

    create_mock.assert_called_once()
    assert create_mock.call_args.kwargs["model"] == client.triage_model
