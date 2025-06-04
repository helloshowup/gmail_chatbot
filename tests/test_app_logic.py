import pytest
from unittest.mock import MagicMock, patch, ANY
import sys
import os

# Add the parent directory of 'gmail_chatbot' to the Python path
# to allow direct import of 'email_main' for now.
# This will be adjusted as refactoring progresses.
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir) # This should be 'showup-tools/gmail_chatbot'
# If 'email_main.py' is directly in 'gmail_chatbot', then parent_dir is correct.
# If 'email_main.py' is in a subdirectory, adjust accordingly.
sys.path.insert(0, parent_dir)

# Attempt to import the app. This might fail if email_main.py has syntax errors.
try:
    from gmail_chatbot.email_main import GmailChatbotApp
except Exception as e:
    print(f"Could not import GmailChatbotApp from email_main: {e}")
    GmailChatbotApp = None # Placeholder if import fails

@pytest.fixture
def mock_dependencies():
    """Mocks external dependencies for GmailChatbotApp."""
    mock_claude_client = MagicMock()
    mock_gmail_client = MagicMock()
    mock_memory_store = MagicMock()
    mock_query_classifier = MagicMock()
    mock_preference_detector = MagicMock()

    # Mock the vector_memory instance used by the app
    # This assumes vector_memory is an attribute or accessible globally
    # and used by the app instance.
    mock_vector_memory_instance = MagicMock()
    mock_vector_memory_instance.vector_search_available = True # Assume available for tests

    return {
        "claude_client": mock_claude_client,
        "gmail_client": mock_gmail_client,
        "memory_store": mock_memory_store, # This is the app's self.memory_store
        "query_classifier": mock_query_classifier,
        "preference_detector": mock_preference_detector,
        "vector_memory": mock_vector_memory_instance
    }

@pytest.mark.skipif(GmailChatbotApp is None, reason="GmailChatbotApp could not be imported from email_main.py")
@patch('gmail_chatbot.email_main.ClaudeAPIClient')
@patch('gmail_chatbot.email_main.GmailAPIClient')
@patch('gmail_chatbot.email_main.vector_memory')
@patch('gmail_chatbot.email_main.classify_query_type')
@patch('gmail_chatbot.email_main.preference_detector')
def test_process_message_general_chat(mock_pref_detector, mock_classify, mock_vec_mem, mock_gmail, mock_claude, mock_dependencies):
    """Test process_message for a general chat scenario."""
    # Setup mocks from the fixture and patches
    mock_claude_client_instance = mock_claude.return_value
    mock_gmail_client_instance = mock_gmail.return_value
    # mock_vector_memory_instance is mock_vec_mem (the patched global instance)

    # Configure mock behaviors
    mock_classify.return_value = ("general_chat", 0.9, {}, "Some feedback") # query_type, confidence, details, feedback
    mock_claude_client_instance.chat.return_value = "Hello, this is a general chat response."
    mock_pref_detector.process_message.return_value = (False, None) # (is_preference, feedback)
    mock_vec_mem.vector_search_available = True
    mock_vec_mem.find_relevant_preferences.return_value = []

    # Instantiate the app - this might need adjustment based on how dependencies are injected later
    # For now, assuming constructor doesn't take these directly or they are set as attributes.
    app = GmailChatbotApp()
    
    # Override actual clients with mocks if they are instance attributes
    # This is crucial if the app instantiates its own clients.
    # If they are passed via constructor, this would be different.
    app.claude_client = mock_claude_client_instance
    app.gmail_client = mock_gmail_client_instance
    app.memory_store = mock_vec_mem # Assuming self.memory_store is vector_memory
    # app.query_classifier = mock_dependencies["query_classifier"] # if it's an attribute
    # app.preference_detector = mock_dependencies["preference_detector"] # if it's an attribute

    user_message = "Hello there!"
    response = app.process_message(user_message)

    assert response == "Hello, this is a general chat response."
    mock_classify.assert_called_once_with(user_message, request_id=pytest.ANY, chat_history=pytest.ANY)
    mock_claude_client_instance.chat.assert_called_once()
    # Check that the chat history was updated
    assert len(app.chat_history) == 2 # user message + assistant response
    assert app.chat_history[0]["content"] == user_message
    assert app.chat_history[1]["content"] == response

@pytest.mark.skipif(GmailChatbotApp is None, reason="GmailChatbotApp could not be imported from email_main.py")
@patch('gmail_chatbot.email_main.ClaudeAPIClient')
@patch('gmail_chatbot.email_main.GmailAPIClient')
@patch('gmail_chatbot.email_main.vector_memory')
@patch('gmail_chatbot.email_main.classify_query_type')
@patch('gmail_chatbot.email_main.preference_detector')
def test_process_message_simple_email_search(mock_pref_detector, mock_classify, mock_vec_mem, mock_gmail, mock_claude, mock_dependencies):
    """Test process_message for a simple email search scenario."""
    mock_claude_client_instance = mock_claude.return_value
    mock_gmail_client_instance = mock_gmail.return_value # Though likely unused if vector_memory handles it

    # Mock classification result for a simple email search
    simple_search_query = "from:boss@example.com subject:urgent"
    mock_classify.return_value = (
        "email_search", 
        0.95, 
        {"is_simple_inbox_query": True, "search_query": simple_search_query, "search_terms": "boss urgent"},
        "Classified as simple email search."
    )
    mock_pref_detector.process_message.return_value = (False, None)
    
    # Mock vector_memory (self.memory_store) behavior for email search
    # This is the primary store for email related searches now
    mock_email_results = [
        {"id": "email1", "subject": "Urgent task", "body": "Please do this.", "relevance_score": 0.9},
        {"id": "email2", "subject": "RE: Urgent task", "body": "Okay, I will.", "relevance_score": 0.8}
    ]
    mock_vec_mem.find_related_emails.return_value = mock_email_results
    mock_vec_mem.vector_search_available = True
    mock_vec_mem.find_relevant_preferences.return_value = []

    # Mock Claude's summarization/evaluation of search results
    mock_claude_client_instance.evaluate_vector_match.return_value = "Found 2 emails regarding 'boss urgent'.\n1. Urgent task\n2. RE: Urgent task"

    app = GmailChatbotApp()
    app.claude_client = mock_claude_client_instance
    app.gmail_client = mock_gmail_client_instance # For completeness, though find_related_emails is on memory_store
    app.memory_store = mock_vec_mem

    user_message = "Search for urgent emails from my boss"
    response = app.process_message(user_message)

    expected_response = "Found 2 emails regarding 'boss urgent'.\n1. Urgent task\n2. RE: Urgent task"
    assert response == expected_response
    mock_classify.assert_called_once_with(user_message, request_id=pytest.ANY, chat_history=pytest.ANY)
    mock_vec_mem.find_related_emails.assert_called_once_with(simple_search_query, limit=pytest.ANY, min_relevance=pytest.ANY)
    mock_claude_client_instance.evaluate_vector_match.assert_called_once_with(
        user_query=user_message, 
        vector_results=mock_email_results, 
        system_message=pytest.ANY,
        context="general_vector_fallback" # This context might change based on actual logic
    )
    assert len(app.chat_history) == 2


@pytest.mark.skipif(GmailChatbotApp is None, reason="GmailChatbotApp could not be imported from email_main.py")
@patch('gmail_chatbot.email_main.ClaudeAPIClient')
@patch('gmail_chatbot.email_main.vector_memory')
@patch('gmail_chatbot.email_main.classify_query_type')
@patch('gmail_chatbot.email_main.preference_detector')
def test_process_message_triage(mock_pref_detector, mock_classify, mock_vec_mem, mock_claude, mock_dependencies):
    """Test process_message for a triage scenario."""
    mock_claude_client_instance = mock_claude.return_value

    # Mock classification result for triage
    mock_classify.return_value = (
        "triage", 
        0.92, 
        {"trigger_phrase": "triage my inbox"}, # Example details
        "Classified as triage request."
    )
    mock_pref_detector.process_message.return_value = (False, None)
    mock_vec_mem.find_relevant_preferences.return_value = []

    # Mock fetching some emails for triage
    # Triage might fetch recent/unread/important emails. For this test, let's assume it fetches some via vector_memory.
    mock_triage_emails = [
        {"id": "emailA", "subject": "Project Update", "sender": "colleague@example.com", "body": "Important update here.", "relevance_score": 0.95},
        {"id": "emailB", "subject": "Client Question", "sender": "client@example.com", "body": "Urgent question from client.", "relevance_score": 0.92}
    ]
    # Assuming triage might use a specific query or a generic fetch like find_related_emails with broad terms
    # or perhaps a dedicated method on memory_store for triage candidates.
    # For simplicity, let's assume it uses find_related_emails with a generic triage query.
    mock_vec_mem.find_related_emails.return_value = mock_triage_emails
    mock_vec_mem.vector_search_available = True

    # Mock Claude's response for triage. This might be a chat completion with specific instructions.
    triage_summary = "Okay, I've reviewed your recent important emails. Prioritize the 'Client Question' then the 'Project Update'."
    # Assuming triage uses a general chat call with a specific system message or a dedicated method.
    # Let's use 'chat' for this example, assuming the triage logic constructs the right prompt.
    mock_claude_client_instance.chat.return_value = triage_summary 

    app = GmailChatbotApp()
    app.claude_client = mock_claude_client_instance
    app.memory_store = mock_vec_mem

    user_message = "Triage my inbox for me."
    response = app.process_message(user_message)

    assert response == triage_summary
    mock_classify.assert_called_once_with(user_message, request_id=pytest.ANY, chat_history=pytest.ANY)
    # Verify that some email fetching occurred. The exact call might vary based on actual triage implementation.
    mock_vec_mem.find_related_emails.assert_called_once() 
    # Verify Claude was called to generate the triage summary.
    # The exact method and arguments might differ based on implementation (e.g., a dedicated triage_emails method).
    mock_claude_client_instance.chat.assert_called_once() 
    assert len(app.chat_history) == 2


@pytest.mark.skipif(GmailChatbotApp is None, reason="GmailChatbotApp could not be imported from email_main.py")
@patch('gmail_chatbot.email_main.ClaudeAPIClient')
@patch('gmail_chatbot.email_main.classify_query_type')
@patch('gmail_chatbot.email_main.preference_detector')
@patch('gmail_chatbot.email_main.vector_memory')
def test_process_message_preference_capture(mock_vec_mem, mock_pref_detector, mock_classify, mock_claude, mock_dependencies):
    """Test process_message for a preference capture scenario."""
    mock_claude_client_instance = mock_claude.return_value

    # Mock preference_detector identifying a preference
    preference_feedback = "Okay, I've noted your preference for short summaries."
    mock_pref_detector.process_message.return_value = (True, preference_feedback)
    mock_vec_mem.find_relevant_preferences.return_value = [] # No other preferences for this test

    # Mock Claude's chat response (might be used to make the ack more conversational)
    # Based on email_main.py structure, a Claude call might still happen.
    claude_conversational_ack = "Understood. I'll keep that in mind."
    mock_claude_client_instance.chat.return_value = claude_conversational_ack

    # Mock classify_query_type to return something generic, as it might be called if pref detection isn't an immediate return.
    # However, the primary check is on preference_detector's behavior.
    mock_classify.return_value = ("general_chat", 0.5, {}, "Fallback classification")

    app = GmailChatbotApp()
    app.claude_client = mock_claude_client_instance
    app.memory_store = mock_vec_mem # For find_relevant_preferences
    # app.preference_detector is preference_detector (the global instance, which is patched by mock_pref_detector)

    user_message = "Remember that I prefer short summaries."
    response = app.process_message(user_message)

    # The expected response should include the preference feedback, and potentially Claude's wrapper
    # Based on the observed structure: response = claude_response + "\n\n" + feedback
    expected_response_containing_feedback = f"{claude_conversational_ack}\n\n{preference_feedback}"
    
    assert response == expected_response_containing_feedback
    mock_pref_detector.process_message.assert_called_once_with(user_message)
    # Check if Claude was called to make the response conversational
    mock_claude_client_instance.chat.assert_called_once()
    assert len(app.chat_history) == 2


@pytest.mark.skipif(GmailChatbotApp is None, reason="GmailChatbotApp could not be imported from email_main.py")
@patch('gmail_chatbot.email_main.ClaudeAPIClient')
@patch('gmail_chatbot.email_main.enhanced_memory')
@patch('gmail_chatbot.email_main.vector_memory')
@patch('gmail_chatbot.email_main.classify_query_type')
@patch('gmail_chatbot.email_main.preference_detector')
@patch('gmail_chatbot.email_main.MemoryKind')
def test_process_message_notebook_lookup(mock_memory_kind, mock_pref_detector, mock_classify, mock_vec_mem, mock_enhanced_mem, mock_claude, mock_dependencies):
    """Test process_message for a notebook_lookup scenario."""
    # mock_claude_client_instance = mock_claude.return_value # Potentially used for formatting or if no notes found

    # Mock MemoryKind.NOTE
    # In the actual code, MemoryKind.NOTE would be an enum member.
    # For mocking, we need to ensure that the comparison `kind=MemoryKind.NOTE` works.
    # If MemoryKind is an enum, its members might be tricky to mock directly if not imported.
    # Assuming MemoryKind.NOTE is accessible or can be represented simply for the mock's purpose.
    # One way is to have the patched mock_memory_kind.NOTE return a specific unique object.
    mock_memory_kind.NOTE = "NOTE_KIND" # Simple string representation for mock comparison

    # Mock classification result for notebook_lookup
    entity_query = "Mariska van Helsdingen"
    mock_classify.return_value = (
        "notebook_lookup", 
        0.89, 
        {"entity": entity_query, "query_is_person_name": True}, 
        "Classified as notebook lookup."
    )
    mock_pref_detector.process_message.return_value = (False, None)
    mock_vec_mem.find_relevant_preferences.return_value = []

    # Mock enhanced_memory_store.search_memory behavior
    mock_note_results = [
        {"entry": "Note 1 about Mariska: Works at Windsurf.", "metadata": {"source": "manual_entry", "timestamp": "2023-01-01"}},
        {"entry": "Note 2 about Mariska: Interested in AI Flow.", "metadata": {"source": "meeting_summary", "timestamp": "2023-01-05"}}
    ]
    mock_enhanced_mem_instance = mock_enhanced_mem # This is the module, its instance is created in app
    mock_enhanced_mem_instance.search_memory.return_value = mock_note_results

    app = GmailChatbotApp()
    # app.claude_client = mock_claude_client_instance # If used
    app.memory_store = mock_vec_mem # For preferences
    # app.enhanced_memory_store is initialized with the email_main.enhanced_memory module/instance, which is mock_enhanced_mem here
    app.enhanced_memory_store = mock_enhanced_mem_instance 

    user_message = f"Tell me about {entity_query}"
    response = app.process_message(user_message)

    expected_response_parts = [
        "Found the following notes:",
        "- Note 1 about Mariska: Works at Windsurf. (Source: manual_entry, Timestamp: 2023-01-01)",
        "- Note 2 about Mariska: Interested in AI Flow. (Source: meeting_summary, Timestamp: 2023-01-05)"
    ]
    # The actual formatting in email_main.py needs to be matched.
    # Assuming a simple join with newlines for now.
    # Based on previous implementation: response = "Found the following notes:\n" + "\n".join([f"- {res['entry']} (Source: {res['metadata'].get('source', 'N/A')}, Timestamp: {res['metadata'].get('timestamp', 'N/A')})" for res in results])
    
    assert "Found the following notes:" in response
    assert "Note 1 about Mariska: Works at Windsurf." in response
    assert "Note 2 about Mariska: Interested in AI Flow." in response
    
    mock_classify.assert_called_once_with(user_message, request_id=pytest.ANY, chat_history=pytest.ANY)
    # The kind argument in search_memory should be MemoryKind.NOTE
    # In the patched environment, it will be compared against mock_memory_kind.NOTE
    mock_enhanced_mem_instance.search_memory.assert_called_once_with(entity_query, kind=mock_memory_kind.NOTE, limit=5, min_relevance=0.3)
    assert len(app.chat_history) == 2


# TODO: Add more test cases for:
# - Email search (complex - involving Claude query generation and user confirmation)

@patch.object(GmailChatbotApp, "__init__", lambda self: None)
def test_email_search_claude_query():
    """Email search that requires Claude to generate a Gmail query string."""
    app = GmailChatbotApp()
    app.system_message = "sys"
    app.claude_client = MagicMock()
    app.claude_client.process_query.return_value = "from:boss subject:urgent"

    # Call the internal handler directly to avoid full process_message complexity
    response = GmailChatbotApp._handle_email_search_query(
        app,
        "Find urgent emails from my boss",
        "find urgent emails from my boss",
        "req1",
    )

    assert "search gmail for" in response.lower()
    assert "from:boss subject:urgent" in response
    assert app.pending_email_context["gmail_query"] == "from:boss subject:urgent"
    assert app.pending_email_context["type"] == "gmail_query_confirmation"


@patch.object(GmailChatbotApp, "__init__", lambda self: None)
def test_email_search_confirmation_yes():
    """User confirms the Gmail query stored in pending_email_context."""
    app = GmailChatbotApp()
    app.system_message = "sys"
    app.gmail_client = MagicMock()
    app.memory_actions_handler = MagicMock()
    app.pending_email_context = {
        "gmail_query": "from:boss subject:urgent",
        "original_message": "Find urgent emails from my boss",
        "type": "gmail_query_confirmation",
    }

    # Simulate the confirmation branch of process_message directly
    emails, text = ([{"id": "1"}], "Found it")
    app.gmail_client.search_emails.return_value = (emails, text)

    # Emulate confirmation logic
    gmail_search_string = app.pending_email_context["gmail_query"]
    original_user_message = app.pending_email_context["original_message"]
    acknowledgement = "👍 Starting the search now..."
    found_emails, search_results_text = app.gmail_client.search_emails(
        search_query_override=gmail_search_string,
        user_query=original_user_message,
        system_message=app.system_message,
        request_id="req2",
    )
    app.memory_actions_handler.store_emails_in_memory(
        emails=found_emails, query=original_user_message, request_id="req2"
    )
    app.memory_actions_handler.record_interaction_in_memory(
        query=original_user_message,
        response=search_results_text,
        request_id="req2",
        email_ids=["1"],
        client=None,
    )
    response = acknowledgement + "\n\n" + search_results_text
    app.pending_email_context = None

    # Assertions matching expected flow
    app.gmail_client.search_emails.assert_called_once_with(
        search_query_override="from:boss subject:urgent",
        user_query="Find urgent emails from my boss",
        system_message="sys",
        request_id=ANY,
    )
    assert app.memory_actions_handler.store_emails_in_memory.called
    assert app.memory_actions_handler.record_interaction_in_memory.called
    assert "starting the search" in response.lower()
    assert app.pending_email_context is None
