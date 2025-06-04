#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Helper utilities providing training examples for preference detection."""

from typing import List


def get_preference_training_data() -> List[str]:
    """Return sample phrases expressing user preferences."""
    return [
        "I prefer dark mode for the interface.",
        "Please don't notify me after 6pm.",
        "I like short summaries of my emails.",
        "Always show me the full email thread when replying.",
        "Stop sending me daily digest emails.",
        "I would rather see only unread messages by default.",
        "Keep my inbox organized by sender.",
        "Don't include attachments in the summary.",
        "Send me a weekly report instead of daily.",
        "Notify me when there's a message from my manager.",
    ]


def get_non_preference_examples() -> List[str]:
    """Return sample phrases that are not preference statements."""
    return [
        "Search my inbox for last week's meeting notes.",
        "What important things are waiting for me today?",
        "Catch me up on recent emails from Alice.",
        "Can you explain what the project update means?",
        "Show me emails from John about invoices.",
        "Do I have any unread messages?",
        "What's on my schedule tomorrow?",
        "Who emailed me yesterday about the contract?",
        "Summarize the conversation with the sales team.",
        "Check if there are any new messages.",
    ]
