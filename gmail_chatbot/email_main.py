"""Backward compatibility wrapper for GmailChatbotApp."""


from gmail_chatbot.app.core import (
    GmailChatbotApp,
    restore_streams,
    wait_for_threads,
    vector_memory,
)

from gmail_chatbot.email_claude_api import ClaudeAPIClient
from gmail_chatbot.email_gmail_api import GmailAPIClient
from gmail_chatbot.email_memory_vector import EmailVectorMemoryStore
from gmail_chatbot.enhanced_memory import EnhancedMemoryStore
import gmail_chatbot.enhanced_memory as enhanced_memory
from gmail_chatbot.memory_handler import MemoryActionsHandler
from gmail_chatbot.memory_models import MemoryKind
from gmail_chatbot.query_classifier import classify_query_type
from gmail_chatbot.preference_detector import PreferenceDetector

# Provide patchable aliases expected by tests
preference_detector = PreferenceDetector
GmailClient = GmailAPIClient

__all__ = [
    "GmailChatbotApp",
    "restore_streams",
    "wait_for_threads",
    "vector_memory",
    "ClaudeAPIClient",
    "GmailAPIClient",
    "EmailVectorMemoryStore",
    "EnhancedMemoryStore",
    "enhanced_memory",
    "MemoryActionsHandler",
    "MemoryKind",
    "classify_query_type",
    "preference_detector",
    "GmailClient",
]
