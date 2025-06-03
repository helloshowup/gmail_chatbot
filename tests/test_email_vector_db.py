import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Adjust sys.path to include the project root ('showup-tools')
# __file__ is .../showup-tools/gmail_chatbot/tests/test_email_vector_db.py
# project_root_dir should be .../showup-tools, which contains the 'gmail_chatbot' package
project_root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root_dir not in sys.path:
    sys.path.insert(0, project_root_dir)

from gmail_chatbot.email_vector_db import EmailVectorDB, EMBEDDING_MODEL_NAME, DEFAULT_CACHE_DIR, VECTOR_LIBS_AVAILABLE
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

    @patch('gmail_chatbot.email_vector_db.HuggingFaceEmbeddings')
    def test_embedding_model_load_os_error(self, mock_huggingface_embeddings):
        """Test EmailVectorDB handles OSError during embedding model initialization."""
        mock_huggingface_embeddings.side_effect = OSError("Simulated OSError: Cannot allocate memory")

        vector_db = EmailVectorDB() # Trigger initialization

        self.assertFalse(vector_db.vector_search_available, "Vector search should be False on OSError")
        self.assertIsNotNone(vector_db.initialization_error_message, "Error message should be set on OSError")
        self.assertIn("OSError", vector_db.initialization_error_message, "Error message should mention OSError")
        self.assertIn("Cannot allocate memory", vector_db.initialization_error_message, "Error message should contain specific OSError text")
        self.assertIn("consider increasing available RAM", vector_db.initialization_error_message, "Error message should suggest remedies")
        
        # Test propagation to EmailVectorMemoryStore
        # Ensure EmailVectorMemoryStore gets a fresh (or the same failed) instance of EmailVectorDB
        if hasattr(EmailVectorMemoryStore, '_instance'): EmailVectorMemoryStore._instance = None
        memory_store = EmailVectorMemoryStore()
        self.assertFalse(memory_store.vector_search_available, "Memory store should reflect vector_db unavailability")
        self.assertEqual(memory_store.get_vector_search_error_message(), vector_db.initialization_error_message, "Memory store error message mismatch")

    @patch('gmail_chatbot.email_vector_db.HuggingFaceEmbeddings')
    def test_embedding_model_load_generic_exception(self, mock_huggingface_embeddings):
        """Test EmailVectorDB handles a generic Exception during embedding model initialization."""
        mock_huggingface_embeddings.side_effect = Exception("Simulated generic exception")

        vector_db = EmailVectorDB()

        self.assertFalse(vector_db.vector_search_available, "Vector search should be False on generic Exception")
        self.assertIsNotNone(vector_db.initialization_error_message, "Error message should be set on generic Exception")
        self.assertIn("Failed to initialize HuggingFaceEmbeddings", vector_db.initialization_error_message, "Error message should indicate embedding init failure")
        self.assertIn("Simulated generic exception", vector_db.initialization_error_message, "Error message should contain specific Exception text")

        if hasattr(EmailVectorMemoryStore, '_instance'): EmailVectorMemoryStore._instance = None
        memory_store = EmailVectorMemoryStore()
        self.assertFalse(memory_store.vector_search_available, "Memory store should reflect unavailability on generic Exception")
        self.assertEqual(memory_store.get_vector_search_error_message(), vector_db.initialization_error_message, "Memory store error message mismatch on generic Exception")

    @patch('gmail_chatbot.email_vector_db.HuggingFaceEmbeddings', None) # Ensure HuggingFaceEmbeddings itself is None
    @patch('gmail_chatbot.email_vector_db.VECTOR_LIBS_AVAILABLE', False) # Mock the global constant in email_vector_db
    def test_vector_libs_not_available(self, mock_huggingface_none, mock_vector_libs_false): # Corrected mock names in signature
        """Test EmailVectorDB handles case where vector libraries are not available."""
        # The patches should ensure VECTOR_LIBS_AVAILABLE is False and HuggingFaceEmbeddings is None
        # when EmailVectorDB is initialized.
        vector_db = EmailVectorDB()

        self.assertFalse(vector_db.vector_search_available, "Vector search should be False if libs not available")
        self.assertIsNotNone(vector_db.initialization_error_message, "Error message should be set if libs not available")
        self.assertIn("Required vector search libraries (e.g., langchain_huggingface) are not installed.", vector_db.initialization_error_message, "Error message for missing libs incorrect")
        
        if hasattr(EmailVectorMemoryStore, '_instance'): EmailVectorMemoryStore._instance = None
        memory_store = EmailVectorMemoryStore()
        self.assertFalse(memory_store.vector_search_available, "Memory store should reflect unavailability if libs missing")
        self.assertEqual(memory_store.get_vector_search_error_message(), vector_db.initialization_error_message, "Memory store error message mismatch for missing libs")

if __name__ == '__main__':
    unittest.main()
