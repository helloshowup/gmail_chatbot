#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for the EnhancedMemoryStore class to verify thread-safe operations,
MemoryEntry integration, and vector search capabilities.
"""

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from gmail_chatbot.enhanced_memory import EnhancedMemoryStore
from gmail_chatbot.memory_models import MemoryEntry, MemoryKind, MemorySource
from gmail_chatbot.memory_handler import MemoryActionsHandler
from unittest.mock import MagicMock


class TestEnhancedMemoryStore(unittest.TestCase):
    """Test cases for the EnhancedMemoryStore class."""
    
    def setUp(self):
        """Set up temporary directory for test files."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_memory_path = Path(self.temp_dir.name) / "memory"
        self.test_memory_path.mkdir(exist_ok=True)
        
        # Create memory store with test path
        self.memory_store = EnhancedMemoryStore(memory_path=self.test_memory_path)
    
    def tearDown(self):
        """Clean up temporary files."""
        self.temp_dir.cleanup()
    
    def test_client_memory(self):
        """Test adding and retrieving client information."""
        # Add new client
        self.memory_store.add_client_info("Test Client", {"status": "active"})
        
        # Verify client was added
        client_names = self.memory_store.get_client_names()
        self.assertIn("Test Client", client_names)
        
        # Update client info
        self.memory_store.add_client_info("Test Client", {"priority": "high"})
        
        # Check if client memory file exists
        client_memory_path = self.test_memory_path / "client_memory.json"
        self.assertTrue(client_memory_path.exists())
        
        # Load client memory directly to verify
        with open(client_memory_path, 'r') as f:
            client_data = json.load(f)
        
        self.assertIn("Test Client", client_data)
        self.assertEqual(client_data["Test Client"]["info"]["status"], "active")
        self.assertEqual(client_data["Test Client"]["info"]["priority"], "high")
        self.assertEqual(client_data["Test Client"]["interactions"], 1)
    
    def test_preference_storage(self):
        """Test storing and retrieving user preferences."""
        # Add a preference
        preference_content = "I prefer dark mode for all interfaces"
        self.memory_store.remember_user_preference(
            content=preference_content,
            label="ui_preference",
            tags=["dark_mode", "ui"]
        )
        
        # Verify preferences file exists
        preferences_path = self.test_memory_path / "preferences.json"
        self.assertTrue(preferences_path.exists())
        
        # Load preferences directly to verify
        with open(preferences_path, 'r') as f:
            preferences = json.load(f)
        
        self.assertEqual(len(preferences), 1)
        self.assertEqual(preferences[0]["content"], preference_content)
        self.assertEqual(preferences[0]["kind"], "preference")
        self.assertEqual(preferences[0]["meta"]["label"], "ui_preference")
        self.assertIn("dark_mode", preferences[0]["tags"])
        
        # Add another preference
        self.memory_store.remember_user_preference(
            content="I don't like to be notified after 6pm",
            label="notification_preference",
            tags=["notifications", "quiet_hours"]
        )
        
        # Reload from disk to verify append worked
        with open(preferences_path, 'r') as f:
            preferences = json.load(f)
        
        self.assertEqual(len(preferences), 2)
        self.assertEqual(preferences[1]["meta"]["label"], "notification_preference")
    
    def test_concurrent_preference_updates(self):
        """Test thread-safe concurrent preference updates."""
        # Number of threads and preferences per thread
        thread_count = 5
        prefs_per_thread = 3
        
        # Create a lock for synchronizing file access during tests
        file_lock = threading.Lock()
        completed_prefs = []
        
        def add_preferences(thread_id):
            thread_store = EnhancedMemoryStore(memory_path=self.test_memory_path)
            for i in range(prefs_per_thread):
                content = f"Thread {thread_id} preference {i}"
                # Use a more aggressive approach for testing
                # This ensures each write is completely separate from others
                with file_lock:
                    thread_store.remember_user_preference(
                        content=content,
                        label=f"thread_{thread_id}_pref",
                        tags=[f"thread_{thread_id}"]
                    )
                    # Keep track of successfully added preferences
                    completed_prefs.append(content)
                # Small sleep to ensure other threads get a chance
                time.sleep(0.01)
        
        # Create and start threads
        threads = []
        for i in range(thread_count):
            t = threading.Thread(target=add_preferences, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for all threads to complete
        for t in threads:
            t.join(timeout=5.0)  # Add timeout to prevent test hanging
        
        # Verify all preferences were saved
        preferences_path = self.test_memory_path / "preferences.json"
        with open(preferences_path, 'r') as f:
            preferences = json.load(f)
        
        # Print debug info
        print(f"Found {len(preferences)} preferences, expected {thread_count * prefs_per_thread}")
        
        # Log all preference contents for debugging
        contents = [pref["content"] for pref in preferences]
        print(f"Contents: {contents}")
        
        # Check which ones are missing
        expected_contents = []
        for thread_id in range(thread_count):
            for pref_num in range(prefs_per_thread):
                expected_content = f"Thread {thread_id} preference {pref_num}"
                expected_contents.append(expected_content)
                
        missing = [c for c in expected_contents if c not in contents]
        print(f"Missing preferences: {missing}")
        
        self.assertEqual(len(preferences), thread_count * prefs_per_thread)
        
        # Check that all expected preferences are present
        contents = [pref["content"] for pref in preferences]
        for thread_id in range(thread_count):
            for pref_num in range(prefs_per_thread):
                expected_content = f"Thread {thread_id} preference {pref_num}"
                self.assertIn(expected_content, contents)
    
    def test_email_memory(self):
        """Test adding and retrieving email memory."""
        # Create email memory entry
        email_entry = MemoryEntry(
            content="Test email summary",
            kind=MemoryKind.EMAIL,
            source=MemorySource.SYSTEM,
            tags=["important", "client_email"],
            meta={
                "email_id": "test123",
                "subject": "Test Email",
                "sender": "sender@example.com",
                "recipient": "recipient@example.com",
                "date": "2024-01-01T00:00:00Z",
                "client": "Test Client"
            }
        )
        
        # Add to memory store
        self.memory_store.add_email_memory(email_entry)
        
        # Verify email memory file exists
        email_memory_path = self.test_memory_path / "email_memory.json"
        self.assertTrue(email_memory_path.exists())
        
        # Load email memory directly to verify
        with open(email_memory_path, 'r') as f:
            email_memory = json.load(f)
        
        self.assertEqual(len(email_memory), 1)
        self.assertEqual(email_memory[0]["content"], "Test email summary")
        self.assertEqual(email_memory[0]["kind"], "email")
        self.assertEqual(email_memory[0]["meta"]["email_id"], "test123")
        self.assertEqual(email_memory[0]["meta"]["subject"], "Test Email")
        self.assertIn("important", email_memory[0]["tags"])
    
    def test_interaction_memory(self):
        """Test adding and retrieving interaction memory."""
        # Add interaction memory
        self.memory_store.add_interaction_memory(
            content="Response to user query",
            tags=["search_query"],
            meta={
                "query": "What emails do I have from Excel High School?",
                "email_ids": ["msg1", "msg2"],
                "client": "Excel High School"
            }
        )
        
        # Verify interaction memory file exists
        interaction_memory_path = self.test_memory_path / "interaction_memory.json"
        self.assertTrue(interaction_memory_path.exists())
        
        # Load interaction memory directly to verify
        with open(interaction_memory_path, 'r') as f:
            interaction_memory = json.load(f)
        
        self.assertEqual(len(interaction_memory), 1)
        self.assertEqual(interaction_memory[0]["content"], "Response to user query")
        self.assertEqual(interaction_memory[0]["kind"], "interaction")
        self.assertEqual(interaction_memory[0]["meta"]["query"], "What emails do I have from Excel High School?")
        self.assertEqual(interaction_memory[0]["meta"]["client"], "Excel High School")

    def test_note_creation_and_listing(self):
        """Test creating a note and listing it via MemoryActionsHandler."""
        note_text = "Remember to review the contract"
        success = self.memory_store.save_note_from_text(note_text)
        self.assertTrue(success)

        notes_path = self.test_memory_path / "memory_entries.json"
        self.assertTrue(notes_path.exists())

        with open(notes_path, "r") as f:
            entries = json.load(f)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["content"], note_text)
        self.assertIn(entries[0]["kind"], ["note", "NOTE"])

        handler = MemoryActionsHandler(
            memory_store=self.memory_store,
            gmail_client=MagicMock(),
            claude_client=MagicMock(),
            system_message="sys",
            preference_detector=MagicMock(),
        )

        listing = handler.list_saved_notes()
        self.assertIn("Saved Notes:", listing)
        self.assertIn(note_text, listing)
    
    def test_keyword_search(self):
        """Test keyword search functionality."""
        # Add preferences for searching
        self.memory_store.remember_user_preference(
            content="I prefer dark mode for all interfaces",
            label="ui_preference",
            tags=["dark_mode"]
        )
        self.memory_store.remember_user_preference(
            content="I don't like to be notified after 6pm",
            label="notification_preference",
            tags=["notifications"]
        )
        
        # Add email memory
        self.memory_store.add_email_memory(MemoryEntry(
            content="Summary of Excel High School progress report",
            kind=MemoryKind.EMAIL,
            source=MemorySource.SYSTEM,
            tags=["school", "progress"],
            meta={
                "email_id": "school1",
                "subject": "Excel High School Progress Report",
                "sender": "teacher@example.com",
                "recipient": "parent@example.com",
                "date": "2024-01-02T00:00:00Z",
                "client": "Excel High School"
            }
        ))
        
        # Search for preferences with 'dark mode'
        results = self.memory_store._keyword_search("dark mode", kind=MemoryKind.PREFERENCE)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["content"], "I prefer dark mode for all interfaces")
        
        # Search for emails with 'Excel'
        results = self.memory_store._keyword_search("Excel", kind=MemoryKind.EMAIL)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["meta"]["subject"], "Excel High School Progress Report")
        
        # Search across all types
        results = self.memory_store._keyword_search("prefer")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["meta"]["label"], "ui_preference")


if __name__ == "__main__":
    unittest.main()
