#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for the DiskStore class to verify thread-safe operations
and proper error handling.
"""

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from gmail_chatbot.disk_store import DiskStore, DiskStoreError


class TestDiskStore(unittest.TestCase):
    """Test cases for the DiskStore class."""
    
    def setUp(self):
        """Set up temporary directory for test files."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_file = Path(self.temp_dir.name) / "test_store.json"
        self.test_file_list = Path(self.temp_dir.name) / "interaction_store.json"
    
    def tearDown(self):
        """Clean up temporary files."""
        self.temp_dir.cleanup()
    
    def test_init(self):
        """Test initialization of DiskStore."""
        store = DiskStore(self.test_file)
        self.assertEqual(store.path, self.test_file)
        self.assertEqual(store.schema_version, 1)
    
    def test_load_empty(self):
        """Test loading from a non-existent file."""
        store = DiskStore(self.test_file)
        data = store.load()
        self.assertEqual(data, {})
        
        # Test list-based store
        list_store = DiskStore(self.test_file_list)
        data = list_store.load()
        self.assertEqual(data, [])
    
    def test_save_load(self):
        """Test saving and loading data."""
        store = DiskStore(self.test_file)
        test_data = {"key": "value", "nested": {"inner": 123}}
        store.save(test_data)
        
        # Load from the same store
        loaded_data = store.load()
        self.assertEqual(loaded_data["key"], "value")
        self.assertEqual(loaded_data["nested"]["inner"], 123)
        
        # Load from a new store instance
        new_store = DiskStore(self.test_file)
        loaded_data = new_store.load()
        self.assertEqual(loaded_data["key"], "value")
        self.assertEqual(loaded_data["nested"]["inner"], 123)
    
    def test_append(self):
        """Test appending to a list-based store."""
        store = DiskStore(self.test_file_list)
        store.append({"id": "1", "content": "test1"})
        store.append({"id": "2", "content": "test2"})
        
        data = store.load()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["id"], "1")
        self.assertEqual(data[1]["content"], "test2")
    
    def test_update(self):
        """Test updating a dict-based store."""
        store = DiskStore(self.test_file)
        store.update("key1", "value1")
        store.update("key2", {"nested": True})
        
        data = store.load()
        self.assertEqual(data["key1"], "value1")
        self.assertEqual(data["key2"]["nested"], True)
    
    def test_concurrent_appends(self):
        """Test concurrent appends from multiple threads."""
        store = DiskStore(self.test_file_list)
        
        # Initialize with empty list
        store.save([])
        
        # Number of threads and appends per thread
        thread_count = 5
        appends_per_thread = 10
        
        def append_items(thread_id):
            thread_store = DiskStore(self.test_file_list)
            for i in range(appends_per_thread):
                item_id = f"thread{thread_id}_item{i}"
                thread_store.append({"id": item_id})
                # Small sleep to increase chance of thread interleaving
                time.sleep(0.01)
        
        # Create and start threads
        threads = []
        for i in range(thread_count):
            t = threading.Thread(target=append_items, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for all threads to complete
        for t in threads:
            t.join()
        
        # Verify results
        data = store.load()
        self.assertEqual(len(data), thread_count * appends_per_thread)
        
        # Check that all expected items are present
        item_ids = [item["id"] for item in data]
        for thread_id in range(thread_count):
            for item_num in range(appends_per_thread):
                expected_id = f"thread{thread_id}_item{item_num}"
                self.assertIn(expected_id, item_ids)
    
    def test_schema_version(self):
        """Test schema version is properly added to dict data."""
        store = DiskStore(self.test_file, schema_version=2)
        store.save({"key": "value"})
        
        # Check the raw file content to verify schema_version was added
        with open(self.test_file, 'r') as f:
            raw_data = json.load(f)
        
        self.assertEqual(raw_data["schema_version"], 2)
        
        # Load through the API and check schema_version
        loaded_data = store.load()
        self.assertEqual(loaded_data["schema_version"], 2)
    
    def test_error_handling(self):
        """Test error handling for invalid operations."""
        dict_store = DiskStore(self.test_file)
        dict_store.save({"key": "value"})
        
        list_store = DiskStore(self.test_file_list)
        list_store.save([{"id": "1"}])
        
        # Test appending to a dict-based store
        with self.assertRaises(DiskStoreError):
            dict_store.append({"id": "2"})
        
        # Test updating a list-based store
        with self.assertRaises(DiskStoreError):
            list_store.update("key", "value")


if __name__ == "__main__":
    unittest.main()
