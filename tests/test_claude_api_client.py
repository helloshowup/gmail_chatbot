import os
import types
from unittest.mock import MagicMock

from gmail_chatbot.email_claude_api import ClaudeAPIClient, CLAUDE_API_KEY_ENV


def test_process_email_content_model_forwarded(monkeypatch):
    os.environ[CLAUDE_API_KEY_ENV] = "test-key"
    mock_response = MagicMock()
    mock_response.content = [types.SimpleNamespace(text="ok")]
    mock_response.usage = types.SimpleNamespace(input_tokens=1, output_tokens=1)
    create_mock = MagicMock(return_value=mock_response)
    mock_client = MagicMock()
    mock_client.messages.create = create_mock
    monkeypatch.setattr("anthropic.Anthropic", lambda api_key: mock_client, raising=False)

    client = ClaudeAPIClient(model="dummy", prep_model="prep-model")
    email_data = {"id": "1"}
    client.process_email_content(email_data, "summary", "sys", model=client.prep_model)

    create_mock.assert_called_once()
    assert create_mock.call_args.kwargs["model"] == client.prep_model
