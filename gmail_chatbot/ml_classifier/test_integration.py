#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test script for the integrated query classifier
"""

import sys
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Add Gmail chatbot path
MODULE_DIR = Path(__file__).parent
GMAIL_DIR = MODULE_DIR.parent
sys.path.insert(0, str(GMAIL_DIR))

# Import the classifier
from gmail_chatbot.query_classifier import (
    classify_query_type,
    get_classification_feedback,
)

# Test queries
TEST_QUERIES = [
    # Clear examples
    "Show me emails from John",  # email_search
    "What needs my attention today?",  # triage
    "Catch me up on my inbox",  # catch_up
    "Can you explain that again?",  # clarify
    "Tell me about email best practices",  # general_chat/chat
    
    # Ambiguous examples
    "Show me important emails",  # could be email_search or triage
    "Check my inbox",  # could be email_search or catch_up
    "help",  # very short, likely clarify with low confidence
    
    # Empty input (should handle gracefully)
    ""
]

def main():
    print("Testing Integrated Query Classifier\n")
    
    for query in TEST_QUERIES:
        try:
            print(f"Query: '{query}'")
            
            # Call the integrated classifier
            classification, confidence, scores = classify_query_type(query)
            
            print(f"  Classification: {classification}")
            print(f"  Confidence: {confidence:.2f}")
            print("  Top scores:")
            
            # Show top 3 scores
            sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
            for category, score in sorted_scores:
                print(f"    {category}: {score:.2f}")
            
            # Check if we get uncertainty feedback
            feedback = get_classification_feedback(classification, confidence)
            if feedback:
                print(f"  Uncertainty feedback: {feedback}")
                
            print()
            
        except Exception as e:
            print(f"  Error: {e}\n")

if __name__ == "__main__":
    main()
