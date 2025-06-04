import unittest
from unittest.mock import patch
import os
import sys

# Adjust sys.path to include the project root ('showup-tools')
# __file__ is .../showup-tools/gmail_chatbot/tests/test_email_vector_db.py
# project_root_dir should be .../showup-tools, which contains the 'gmail_chatbot' package
project_root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root_dir not in sys.path:
    sys.path.insert(0, project_root_dir)

from gmail_chatbot.email_vector_db import EmailVectorDB
from gmail_chatbot.email_memory_vector import EmailVectorMemoryStore

class TestEmailVectorDBErrorHandling(unittest.TestCase):

    def setUp(self):
        """Reset singletons for test isolation."""
        # Reset EmailVectorDB singleton
        if hasattr(EmailVectorDB, '_instance'):
            EmailVectorDB._instance = None
        
        # Reset EmailVectorMemoryStore singleton (if it is one) or its cached db instance
        # This assumes EmailVectorMemoryStore might also follow a singleton pattern or cache vector_db
        if hasattr(EmailVectorMemoryStore, '_instance'): 
            EmailVectorMemoryStore._instance = None
        # If EmailVectorMemoryStore directly caches the vector_db instance, clear that too
        # This depends on EmailVectorMemoryStore's implementation details.
        # For now, we assume resetting EmailVectorDB._instance is the primary concern.
        # A more robust way would be to patch EmailVectorDB.__new__ or its instance retrieval.

    @patch('gmail_chatbot.email_vector_db.VECTOR_LIBS_AVAILABLE', True)
    @patch('gmail_chatbot.email_vector_db.HuggingFaceEmbeddings', create=True)
    def test_embedding_model_load_os_error(self, mock_huggingface_embeddings):
        """Test EmailVectorDB handles OSError during embedding model initialization."""
        mock_huggingface_embeddings.side_effect = OSError("Simulated OSError: Cannot allocate memory")

        vector_db = EmailVectorDB() # Trigger initialization

        self.assertFalse(vector_db.vector_search_available, "Vector search should be False on OSError")
        self.assertIsNotNone(vector_db.initialization_error_message, "Error message should be set on OSError")
        self.assertIn("OSError", vector_db.initialization_error_message, "Error message should mention OSError")
        self.assertIn("Cannot allocate memory", vector_db.initialization_error_message, "Error message should contain specific OSError text")
        self.assertIn("more RAM", vector_db.initialization_error_message, "Error message should suggest remedies")
        
        # Test propagation to EmailVectorMemoryStore
        # Ensure EmailVectorMemoryStore gets a fresh (or the same failed) instance of EmailVectorDB
        if hasattr(EmailVectorMemoryStore, '_instance'): EmailVectorMemoryStore._instance = None
        memory_store = EmailVectorMemoryStore()
        self.assertFalse(memory_store.vector_search_available, "Memory store should reflect vector_db unavailability")
        self.assertFalse(memory_store.vector_search_available, "Memory store should reflect vector_db unavailability")
        self.assertIsNotNone(memory_store.get_vector_search_error_message())

    @patch('gmail_chatbot.email_vector_db.VECTOR_LIBS_AVAILABLE', True)
    @patch('gmail_chatbot.email_vector_db.HuggingFaceEmbeddings', create=True)
    def test_embedding_model_load_generic_exception(self, mock_huggingface_embeddings):
        """Test EmailVectorDB handles a generic Exception during embedding model initialization."""
        mock_huggingface_embeddings.side_effect = Exception("Simulated generic exception")

        vector_db = EmailVectorDB()

        self.assertFalse(vector_db.vector_search_available, "Vector search should be False on generic Exception")
        self.assertIsNotNone(vector_db.initialization_error_message, "Error message should be set on generic Exception")
        self.assertIn("failed to load", vector_db.initialization_error_message.lower(),
                      "Error message should indicate embedding init failure")
        self.assertIn("Simulated generic exception", vector_db.initialization_error_message,
                      "Error message should contain specific Exception text")

        if hasattr(EmailVectorMemoryStore, '_instance'): EmailVectorMemoryStore._instance = None
        memory_store = EmailVectorMemoryStore()
        self.assertFalse(memory_store.vector_search_available, "Memory store should reflect unavailability on generic Exception")
        self.assertFalse(memory_store.vector_search_available)
        self.assertIsNotNone(memory_store.get_vector_search_error_message())

    @patch('gmail_chatbot.email_vector_db.HuggingFaceEmbeddings', None, create=True)
    @patch('gmail_chatbot.email_vector_db.VECTOR_LIBS_AVAILABLE', False)
    def test_vector_libs_not_available(self):
        """Test EmailVectorDB handles case where vector libraries are not available."""
        # The patches should ensure VECTOR_LIBS_AVAILABLE is False and HuggingFaceEmbeddings is None
        # when EmailVectorDB is initialized.
        vector_db = EmailVectorDB()

        self.assertFalse(vector_db.vector_search_available, "Vector search should be False if libs not available")
        self.assertIsNotNone(vector_db.initialization_error_message, "Error message should be set if libs not available")
        self.assertIn("vector search libraries", vector_db.initialization_error_message.lower(),
                      "Error message for missing libs incorrect")
        
        if hasattr(EmailVectorMemoryStore, '_instance'):
            EmailVectorMemoryStore._instance = None
        memory_store = EmailVectorMemoryStore()
        self.assertFalse(memory_store.vector_search_available)
        self.assertIsNotNone(memory_store.get_vector_search_error_message())

if __name__ == '__main__':
    unittest.main()
