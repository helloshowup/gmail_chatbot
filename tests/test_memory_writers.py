# test_memory_writers.py
import unittest
from unittest.mock import MagicMock
from datetime import date, datetime

# Import the modules under test
from gmail_chatbot.memory_writers import (
    store_professional_context,
    format_research_payload,
)


class TestMemoryWriters(unittest.TestCase):
    """Tests for the memory_writers module."""
    
    def setUp(self):
        """Set up test environment."""
        # Create a mock memory store for testing
        self.memory_store = MagicMock()
        self.memory_store.memory_entries = []
        self.memory_store.add_memory_entry = MagicMock(return_value=True)
        
        # Test date for consistency
        self.test_date = date(2025, 6, 2)
        
        # Sample research data for testing
        self.research_data = {
            'clients': [
                {
                    'name': 'Test Client',
                    'emails_count': 5,
                    'status': 'active'
                },
                {
                    'name': 'Inactive Client',
                    'emails_count': 0,
                    'status': 'error'
                }
            ],
            'projects': [
                {
                    'name': 'Test Project',
                    'deadline': '2025-07-01',
                    'status': 'in progress'
                }
            ]
        }
    
    def test_format_research_payload(self):
        """Test that research data is correctly formatted into human-readable text"""
        formatted_content = format_research_payload(self.research_data)
        
        # Verify basic structure and content
        self.assertIn('Snapshot of current professional landscape', formatted_content)
        self.assertIn('(2 clients, 1 active projects)', formatted_content)
        self.assertIn('**Clients:**', formatted_content)
        self.assertIn('**Test Client**', formatted_content)
        self.assertIn('**Projects:**', formatted_content)
        self.assertIn('**Test Project**', formatted_content)
        
        # Verify specific formatting elements
        self.assertIn('✅', formatted_content)  # Active status indicator
        self.assertIn('⚠️', formatted_content)  # Error status indicator
        self.assertIn('5 recent emails', formatted_content)
        self.assertIn('Deadline: 2025-07-01', formatted_content)
    
    def test_store_professional_context_success(self):
        """Test successful storage of professional context."""
        # Set up test data
        title = 'Test Professional Context'
        content = 'Test content with summary'
        
        # Call the function under test
        store_professional_context(
            memory_store=self.memory_store,
            title=title,
            content=content,
            date_obj=self.test_date
        )
        
        # Verify the memory store was called correctly
        self.memory_store.add_memory_entry.assert_called_once()
        
        # Verify the entry structure
        call_args = self.memory_store.add_memory_entry.call_args[0][0]
        self.assertEqual(call_args['title'], title)
        self.assertEqual(call_args['content'], content)
        self.assertEqual(call_args['type'], 'professional_context')
        self.assertEqual(datetime.fromisoformat(call_args['date']).date(), self.test_date)
        self.assertIn('professional_context', call_args['tags'])
    
    def test_store_professional_context_duplicate_guard(self):
        """Test that duplicates for the same date are prevented"""
        # Set up existing entry for today
        today_iso = datetime.combine(self.test_date, datetime.min.time()).isoformat()
        
        # Add an existing entry with today's date
        self.memory_store.memory_entries = [
            {
                'id': f'prof_context_{self.test_date.isoformat()}',
                'title': 'Existing Entry',
                'content': 'Already logged today',
                'type': 'professional_context',
                'date': today_iso,
                'tags': ['professional_context']
            }
        ]
        
        # Attempt to store another entry for today
        with self.assertRaises(ValueError) as context:
            store_professional_context(
                memory_store=self.memory_store,
                title='New Entry',
                content='Should not be stored',
                date_obj=self.test_date
            )
        
        # Verify the error message
        self.assertIn(f'Professional context already logged for {self.test_date}', str(context.exception))
        
        # Verify add_memory_entry was not called
        self.memory_store.add_memory_entry.assert_not_called()
    
    def test_store_professional_context_fail_fast(self):
        """Test that storage failures raise exceptions (fail-fast behavior)"""
        # Set up the mock to simulate a storage failure
        self.memory_store.add_memory_entry = MagicMock(return_value=False)
        
        # Attempt to store an entry
        with self.assertRaises(RuntimeError) as context:
            store_professional_context(
                memory_store=self.memory_store,
                title='Failed Entry',
                content='Should raise error',
                date_obj=self.test_date
            )
        
        # Verify the error message
        self.assertIn('Failed to store professional context', str(context.exception))


if __name__ == '__main__':
    unittest.main()
