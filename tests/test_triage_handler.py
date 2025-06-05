from unittest.mock import MagicMock

from gmail_chatbot.handlers.triage import handle_triage_query


def _setup_app(summary_return="summary", urgent_count=2):
    app = MagicMock()
    app.system_message = "sys"
    app.has_recent_assistant_phrase.return_value = False
    app.memory_actions_handler.get_action_items_structured.return_value = [
        {"subject": "Finish report", "client": "Acme", "date": "2024-05-01"}
    ]
    app.memory_actions_handler.get_delegation_candidates.return_value = []
    app.memory_actions_handler.is_vector_search_available.return_value = True
    urgent = [
        {
            "subject": "ASAP Meeting",
            "summary": "Need to meet ASAP",
            "client": "Acme",
            "date": "2024-05-02",
        },
        {
            "subject": "Urgent: Sign",
            "summary": "Please sign urgent",
            "client": "Beta",
            "date": "2024-05-03",
        },
    ]
    app.memory_actions_handler.find_related_emails.return_value = urgent[
        :urgent_count
    ]
    app.claude_client.summarize_triage.return_value = summary_return
    return app


def test_handle_triage_returns_claude_summary():
    app = _setup_app("Great summary")
    response = handle_triage_query(app, "triage", "req", {"triage": 1.0})
    assert response == "Great summary"
    app.claude_client.summarize_triage.assert_called_once()


def test_handle_triage_claude_failure_falls_back():
    app = _setup_app("ERROR: fail")
    response = handle_triage_query(app, "triage", "req", {"triage": 1.0})
    assert "Urgent Emails Detected" in response
    assert "ASAP Meeting" in response
    assert "Urgent: Sign" in response


def test_handle_triage_with_claude_summary():
    """Verify summarize_triage is invoked with action items and urgent emails."""
    summary = "Mock triage summary"
    app = _setup_app(summary)
    response = handle_triage_query(app, "triage", "id123", {"triage": 0.9})

    assert response == summary
    expected_actions = app.memory_actions_handler.get_action_items_structured.return_value
    expected_urgent = app.memory_actions_handler.find_related_emails.return_value
    app.claude_client.summarize_triage.assert_called_once_with(
        expected_actions,
        expected_urgent,
        request_id="id123",
    )
