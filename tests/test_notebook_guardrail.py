#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for notebook search guard-rail to prevent hallucinations
when no relevant notebook entries are found.
"""

import sys
import os
import pytest
from unittest.mock import MagicMock

# Add parent directory to path to import module being tested
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import modules to test
from gmail_chatbot.email_main import GmailChatbotApp
from gmail_chatbot.prompt_templates import NOTEBOOK_NO_RESULTS_TEMPLATES
from gmail_chatbot.email_config import CLAUDE_API_KEY_ENV


@pytest.fixture
def mock_deps(monkeypatch):
    """Create mock dependencies for testing."""
    os.environ[CLAUDE_API_KEY_ENV] = "test-key"
    memory_store = MagicMock()
    gmail_client = MagicMock()
    gmail_client.search_emails.return_value = ([], "No emails found")
    claude_client = MagicMock()

    monkeypatch.setattr('gmail_chatbot.email_main.GmailAPIClient', lambda *a, **k: gmail_client)
    monkeypatch.setattr('gmail_chatbot.app.core.GmailAPIClient', lambda *a, **k: gmail_client)
    monkeypatch.setattr('gmail_chatbot.email_main.ClaudeAPIClient', lambda *a, **k: claude_client)
    monkeypatch.setattr('gmail_chatbot.app.core.ClaudeAPIClient', lambda *a, **k: claude_client)
    monkeypatch.setattr('gmail_chatbot.app.core.classify_query_type', lambda q, classifier=None: ("notebook_lookup", 0.8, {"notebook_lookup": 0.8}))
    monkeypatch.setattr('gmail_chatbot.email_main.EmailVectorMemoryStore', lambda *a, **k: memory_store)
    monkeypatch.setattr('gmail_chatbot.app.core.EmailVectorMemoryStore', lambda *a, **k: memory_store)
    monkeypatch.setattr('gmail_chatbot.email_main.EnhancedMemoryStore', MagicMock(return_value=MagicMock()))
    monkeypatch.setattr('gmail_chatbot.app.core.EnhancedMemoryStore', MagicMock(return_value=MagicMock()))
    pref_mock = MagicMock()
    pref_mock.process_message.return_value = (False, None)
    monkeypatch.setattr('gmail_chatbot.email_main.PreferenceDetector', MagicMock(return_value=pref_mock))
    monkeypatch.setattr('gmail_chatbot.app.core.PreferenceDetector', MagicMock(return_value=pref_mock))
    mah_mock = MagicMock()
    monkeypatch.setattr('gmail_chatbot.email_main.MemoryActionsHandler', MagicMock(return_value=mah_mock))
    monkeypatch.setattr('gmail_chatbot.app.core.MemoryActionsHandler', MagicMock(return_value=mah_mock))
    
    app = GmailChatbotApp()
    app.memory_store = memory_store
    app.gmail_client = gmail_client
    app.claude_client = claude_client
    app.memory_actions_handler = MagicMock()
    app.memory_actions_handler.query_memory.side_effect = (
        lambda message, request_id=None: memory_store.search_notebook(message)
    )
    app.memory_actions_handler.store_emails_in_memory = MagicMock()
    app.memory_actions_handler.record_interaction_in_memory = MagicMock()
    app.memory_actions_handler.get_pending_proactive_summaries.return_value = []
    
    return {
        'app': app,
        'memory_store': memory_store,
        'gmail_client': gmail_client,
        'claude_client': claude_client
    }
    
@pytest.mark.parametrize(
    "query,expected_entity",
    [
        ("Tell me about John", "John"),
        ("Who is Robert", "Robert"),
        ("What is Project Alpha", "Project Alpha"),
        ("Information on quarterly results", "quarterly results"),
        ("Generic query without entity", None)
    ]
)
def test_notebook_guardrail_entity_extraction(mock_deps, query, expected_entity, monkeypatch):
    """Test that the guard-rail correctly extracts entities from different query patterns."""
    # Setup mocks
    app = mock_deps['app']
    memory_store = mock_deps['memory_store']
    
    # Mock the classifier to always return notebook_lookup
    monkeypatch.setattr('gmail_chatbot.email_main.classify_query_type',
                         lambda q: ("notebook_lookup", 0.8, {"notebook_lookup": 0.8}))
    
    # Setup - notebook lookup returns empty results
    memory_store.search_notebook.return_value = []

    # Execute
    response = app.process_message(query, "test-123")
    
    if expected_entity:
        assert expected_entity in response
        assert "don't have notes on" in response
        expected_query = (
            f"from:{expected_entity} OR to:{expected_entity} OR subject:{expected_entity}"
        )
    else:
        assert response.startswith(NOTEBOOK_NO_RESULTS_TEMPLATES["generic"])
        expected_query = query

    mock_deps["gmail_client"].search_emails.assert_called_with(
        query=expected_query,
        original_user_query=query,
        system_message=app.system_message,
        request_id="test-123",
    )
        
def test_notebook_guardrail_empty_results(mock_deps, monkeypatch):
    """Test that the guard-rail prevents hallucination when notebook search returns no results."""
    # Setup mocks
    app = mock_deps['app']
    memory_store = mock_deps['memory_store']
    claude_client = mock_deps['claude_client']
    
    # Mock the classifier to always return notebook_lookup
    monkeypatch.setattr('gmail_chatbot.email_main.classify_query_type',
                         lambda q: ("notebook_lookup", 0.8, {"notebook_lookup": 0.8}))
    
    # Setup - notebook lookup returns empty results
    memory_store.search_notebook.return_value = []
    
    # Test query with entity
    test_query = "Tell me about John"
    request_id = "test-123"
    
    # Execute
    response = app.process_message(test_query, request_id)

    # Verify - should return the guard-rail message, not call Claude
    expected_text = NOTEBOOK_NO_RESULTS_TEMPLATES['with_entity'].format(entity="John")
    assert "John" in response
    assert "don't have notes" in response
    # Claude should not be called with no notebook results
    assert not claude_client.generate_response.called
    mock_deps["gmail_client"].search_emails.assert_called_once()
    assert not app.memory_actions_handler.store_emails_in_memory.called
    
def test_notebook_guardrail_with_results(mock_deps, monkeypatch):
    """Test that the guard-rail allows Claude to respond when notebook search returns results."""
    # Setup mocks
    app = mock_deps['app']
    memory_store = mock_deps['memory_store']
    claude_client = mock_deps['claude_client']
    
    # Mock the classifier to always return notebook_lookup
    monkeypatch.setattr('gmail_chatbot.email_main.classify_query_type',
                         lambda q: ("notebook_lookup", 0.8, {"notebook_lookup": 0.8}))
    
    # Setup - notebook lookup returns non-empty results
    memory_store.search_notebook.return_value = [
        {"title": "Notes on John", "content": "John is a software engineer."}
    ]
    claude_client.generate_response.return_value = "John is a software engineer based in Seattle."
    
    # Test query with entity
    test_query = "Tell me about John"
    request_id = "test-123"
    
    # Execute
    response = app.process_message(test_query, request_id)


    # Verify - should call Claude with the notebook entry
    assert "don't have notes" not in response
    assert claude_client.generate_response.called
    app.gmail_client.search_emails.assert_not_called()


def test_notebook_guardrail_gmail_results_stored(mock_deps, monkeypatch):
    """When notebook has no results but Gmail does, emails are stored."""
    app = mock_deps['app']
    memory_store = mock_deps['memory_store']
    gmail_client = mock_deps['gmail_client']

    monkeypatch.setattr('gmail_chatbot.email_main.classify_query_type',
                         lambda q: ("notebook_lookup", 0.8, {"notebook_lookup": 0.8}))

    memory_store.search_notebook.return_value = []
    gmail_client.search_emails.return_value = (
        [{"id": "1", "subject": "hi"}],
        "Found 1 email"
    )

    response = app.process_message("Tell me about John", "req-1")

    gmail_client.search_emails.assert_called_once()
    app.memory_actions_handler.store_emails_in_memory.assert_called_once()
    assert "Found 1 email" in response


