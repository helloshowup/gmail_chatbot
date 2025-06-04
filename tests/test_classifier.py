#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import pytest
from pathlib import Path

# Add parent directory to path for imports
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

# Import query_classifier
from gmail_chatbot.query_classifier import classify_query_type


@pytest.mark.parametrize(
    "query,expected_type", [
        # Email search queries - should all be classified as email_search
        ("Did I receive any emails today?", "email_search"),
        ("Have I received any emails since this morning?", "email_search"),
        ("Show me what hit my inbox yesterday", "email_search"),
        ("Check my inbox for new messages", "email_search"),
        ("Catch me up on what I missed in my inbox", "email_search"),
        ("Can you check todays email?", "email_search"),
        ("search Gmail for from:bryce@example.com", "email_search"),
        ("check today's email", "email_search"),
        ("tell me about todays email?", "email_search"),
        
        # Guard-rail heuristic should catch these
        ("Did I get any emails today?", "email_search"),
        ("Have I got any new mail today?", "email_search"),
        ("Are there any emails for me?", "email_search"),
        
        # Queries that fall back to ambiguous classification
        ("What have I missed since yesterday?", "ambiguous"),
        ("Catch me up on the project status", "ambiguous"),
        ("What's happened since I was away?", "ambiguous"),

        # These triage-style queries are treated as email_search by the regex
        ("What needs my attention today?", "email_search"),
        ("Show me urgent emails I haven't replied to", "email_search"),
        ("What important things are waiting for me?", "ambiguous"),
    ]
)
def test_query_classification(query, expected_type):
    """Test that queries are classified correctly with the right intent."""
    classified_type, confidence, _ = classify_query_type(query)
    assert classified_type == expected_type, f"Query '{query}' was classified as '{classified_type}' but should be '{expected_type}'"
    # Confidence should meet the classifier's minimum threshold
    assert confidence >= 0.1, f"Confidence for '{query}' was only {confidence:.2f}, expected >= 0.1"


def test_heuristic_email_check_override():
    """Test the heuristic override for email check queries."""
    # These are the types of queries that previously might have been misclassified
    # but should now be correctly classified as email_search
    email_check_queries = [
        "Did I receive any emails today?",
        "Check if I got new messages",
        "Do I have any unread messages?",
        "Have I gotten any emails lately?"
    ]
    
    for query in email_check_queries:
        classified_type, confidence, _ = classify_query_type(query)
        assert classified_type == "email_search", f"Email check query '{query}' was not classified as email_search"
        assert confidence >= 0.1, f"Confidence for '{query}' was only {confidence:.2f}, expected >= 0.1"


if __name__ == "__main__":
    # Simple manual testing
    queries_to_test = [
        "Did I receive any emails today?",
        "Catch me up on what I missed in my inbox",
        "What have I missed since yesterday?",
        "What needs my attention today?"
    ]
    
    for query in queries_to_test:
        result = classify_query_type(query)
        print(f"Query: '{query}'")
        print(f"  Classification: {result[0]}")
        print(f"  Confidence: {result[1]:.2f}")
        print("---")
