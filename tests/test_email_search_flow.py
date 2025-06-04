#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import logging
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Add parent directory to path for imports
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

# Import the main application
from gmail_chatbot.email_main import GmailChatbotApp


class TestEmailSearchFlow:
    """Integration tests for the email search query flow."""

    @pytest.fixture
    def mock_gmail_client(self):
        """Create a mock Gmail client for testing."""
        mock_client = MagicMock()
        # Mock search_emails to return some test emails
        mock_client.search_emails.return_value = (
            [
                {"id": "1", "subject": "Test Email 1", "snippet": "This is a test email"},
                {"id": "2", "subject": "Test Email 2", "snippet": "Another test email"},
            ],
            "Found results",
        )
        return mock_client

    @pytest.fixture
    def app(self, mock_gmail_client):
        """Create a test instance of the GmailChatbotApp with mocked dependencies."""
        with patch('gmail_chatbot.app.core.GmailAPIClient', return_value=mock_gmail_client):
            app = GmailChatbotApp()
            app.gmail_client = mock_gmail_client
            app.cl_client = MagicMock()  # Mock Claude client
            yield app

    @pytest.mark.parametrize(
        "query", [
            # Direct email search queries
            "Show me emails from John",
            "Search my inbox for invoices",
            "search Gmail for from:bryce@example.com",
            
            # Inbox check queries that should be routed to email_search
            "Did I receive any emails today?",
            "check today's email",
            "Check my inbox for new messages",
            "Have I got mail today?",
            "Any new messages in my inbox?",
            "Do I have new mail in my inbox?",
            "What hit my inbox today?",
        ]
    )
    def test_email_search_routing(self, app, mock_gmail_client, query, caplog):
        """Email search should run only after confirmation."""
        caplog.set_level(logging.CRITICAL)

        # First call sets a pending confirmation
        response = app.process_message(query)
        assert app.pending_email_context is not None
        mock_gmail_client.search_emails.assert_not_called()

        # Confirm the search
        response = app.process_message("yes")

        mock_gmail_client.search_emails.assert_called_once()

        # Verify the response indicates a search was performed
        assert "found" in response.lower() or "searched" in response.lower() or "results" in response.lower()

        # Ensure a critical log was emitted for the user-initiated search
        assert any(
            "user-initiated search_emails using" in rec.getMessage()
            for rec in caplog.records
            if rec.levelno == logging.CRITICAL
        )

    def test_catch_up_not_triggering_email_search(self, app, mock_gmail_client):
        """Test that catch_up queries do not trigger email searches."""
        # Process a catch_up message
        query = "What's been happening while I was away?"
        app.process_message(query)
        
        # Verify search_emails was not called
        mock_gmail_client.search_emails.assert_not_called()
        
    def test_heuristic_override_logging(self, app, mock_gmail_client):
        """Test that the heuristic override is logged properly."""
        with patch('gmail_chatbot.email_main.logging.info') as mock_logging:
            # Use a query that might have been misclassified before
            query = "Did I receive any emails today?"
            app.process_message(query)
            
            # Check for heuristic override log message (in practice, this would be in query_classifier.py)
            # But since we patch logging.info in the email_main module, this is a simplification
            # In a real implementation, we'd need to patch the logger in query_classifier
            mock_logging.assert_any_call(pytest.approx(r".*\[HEURISTIC\].*", regex=True))
