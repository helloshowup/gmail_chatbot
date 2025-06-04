import pytest
from unittest.mock import MagicMock

from gmail_chatbot.handlers.triage import handle_triage_query


def test_handle_triage_with_urgent_search():
    app = MagicMock()
    app.system_message = "sys"
    app.has_recent_assistant_phrase.return_value = False

    # Action items returned
    app.memory_actions_handler.get_action_items_structured.return_value = [
        {"subject": "Finish report", "client": "Acme", "date": "2024-05-01"}
    ]
    app.memory_actions_handler.get_delegation_candidates.return_value = []
    app.memory_actions_handler.is_vector_search_available.return_value = True
    app.memory_actions_handler.find_related_emails.return_value = [
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

    response = handle_triage_query(app, "triage", "req", {"triage": 1.0})

    assert "Urgent Emails Detected" in response
    assert "ASAP Meeting" in response
    assert "Urgent: Sign" in response
