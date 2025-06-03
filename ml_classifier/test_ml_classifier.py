#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Simple test script for the ML Query Classifier
"""

import sys
from pathlib import Path

# Add module directory to path
ROOT_DIR = Path(__file__).parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Import the classifier lazily to avoid import errors during test collection
try:
    from ml_query_classifier import predict
except Exception:  # pragma: no cover - if dependencies are missing
    predict = None

# Test queries
TEST_QUERIES = [
    # Clear examples
    "Show me emails from John",  # email_search
    "What needs my attention today?",  # triage
    "Catch me up on my inbox",  # catch_up
    "Can you explain that again?",  # clarify
    "Tell me about email best practices",  # general_chat
    
    # Ambiguous examples
    "Show me important emails",  # could be email_search or triage
    "Check my inbox",  # could be email_search or catch_up
    "help",  # very short, likely clarify with low confidence
    
    # Empty input (should handle gracefully)
    ""
]

def main():
    print("Testing ML Query Classifier\n")
    
    for query in TEST_QUERIES:
        try:
            print(f"Query: '{query}'")
            label, confidence, probs = predict(query)
            print(f"  Classification: {label}")
            print(f"  Confidence: {confidence:.2f}")
            print("  Top probabilities:")
            
            # Show top 3 probabilities
            sorted_probs = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:3]
            for category, prob in sorted_probs:
                print(f"    {category}: {prob:.2f}")
                
            print()
            
        except Exception as e:
            print(f"  Error: {e}\n")

if __name__ == "__main__":
    main()
