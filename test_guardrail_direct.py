import os
import sys
from unittest.mock import MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import modules to test
from email_main import GmailChatbotApp
from prompt_templates import NOTEBOOK_NO_RESULTS_TEMPLATES

def run_test():
    print("Starting notebook guardrail test...")
    
    # Create mock dependencies
    memory_store = MagicMock()
    gmail_client = MagicMock()
    claude_client = MagicMock()
    
    # Create app with mocked dependencies
    app = GmailChatbotApp(
        memory_store=memory_store,
        gmail_client=gmail_client,
        claude_client=claude_client
    )
    
    # Setup for notebook lookup with empty results
    memory_store.search_notebook.return_value = []
    
    # Test case 1: Query with entity, no results
    test_query = "Tell me about John"
    request_id = "test-123"
    
    # Mock the query classification
    original_classify = __import__('email_main').classify_query_type
    __import__('email_main').classify_query_type = lambda q: ("notebook_lookup", 0.8, {"notebook_lookup": 0.8})
    
    try:
        # Execute
        response = app.process_message(test_query, request_id)
        
        # Verify response
        print(f"\nResponse: {response}")
        print(f"Contains 'John': {'John' in response}")
        print(f"Contains 'don\'t have notes': {'don\'t have notes' in response}")
        print(f"Claude generate_response called: {claude_client.generate_response.called}")
        
        # Test case 2: With notebook results
        print("\nTesting with notebook results...")
        memory_store.search_notebook.return_value = [
            {"title": "Notes on John", "content": "John is a software engineer."}
        ]
        claude_client.generate_response.return_value = "John is a software engineer based in Seattle."
        
        response = app.process_message(test_query, request_id)
        print(f"Response: {response}")
        print(f"Contains 'don\'t have notes': {'don\'t have notes' in response}")
        print(f"Claude generate_response called: {claude_client.generate_response.called}")
        
        # Test case 3: Entity extraction
        print("\nTesting entity extraction...")
        memory_store.search_notebook.return_value = []
        test_cases = [
            ("Tell me about Jane", "Jane"),
            ("Who is Robert", "Robert"),
            ("What is Project Alpha", "Project Alpha"),
            ("Information on quarterly results", "quarterly results"),
            ("Generic query without entity", None)
        ]
        
        for query, expected_entity in test_cases:
            response = app.process_message(query, "test-123")
            contains_entity = expected_entity and expected_entity in response
            is_generic = expected_entity is None and response == NOTEBOOK_NO_RESULTS_TEMPLATES['generic']
            print(f"Query: {query} | Entity found: {contains_entity} | Uses generic template: {is_generic}")
        
        print("\nAll tests completed!")
    finally:
        # Restore original function
        __import__('email_main').classify_query_type = original_classify

if __name__ == "__main__":
    run_test()
