#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for the MemoryEntry dataclass to ensure proper serialization,
deserialization, and conversion from legacy formats.
"""

import unittest
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from gmail_chatbot.memory_models import MemoryEntry, MemoryKind, MemorySource


class TestMemoryEntry(unittest.TestCase):
    """Test cases for the MemoryEntry dataclass."""
    
    def test_initialization(self):
        """Test basic initialization of MemoryEntry."""
        entry = MemoryEntry(
            content="Test content",
            kind=MemoryKind.NOTE,
            tags=["test", "example"],
            source=MemorySource.USER
        )
        
        self.assertIsNotNone(entry.id)
        self.assertEqual(entry.content, "Test content")
        self.assertEqual(entry.kind, MemoryKind.NOTE)
        self.assertEqual(entry.tags, ["test", "example"])
        self.assertEqual(entry.source, MemorySource.USER)
        self.assertIsInstance(entry.ts, datetime)
        self.assertEqual(entry.meta, {})
    
    def test_serialization(self):
        """Test serialization to dict for JSON storage."""
        ts = datetime(2025, 6, 1, 12, 30, 0)
        entry = MemoryEntry(
            id="test123",
            content="Serialization test",
            kind=MemoryKind.PREFERENCE,
            tags=["serialization"],
            ts=ts,
            source=MemorySource.SYSTEM,
            meta={"label": "test_label"}
        )
        
        # Convert to dict
        entry_dict = entry.to_dict()
        
        # Check values
        self.assertEqual(entry_dict["id"], "test123")
        self.assertEqual(entry_dict["content"], "Serialization test")
        self.assertEqual(entry_dict["kind"], "preference")
        self.assertEqual(entry_dict["tags"], ["serialization"])
        self.assertEqual(entry_dict["ts"], "2025-06-01T12:30:00")
        self.assertEqual(entry_dict["source"], "system")
        self.assertEqual(entry_dict["meta"], {"label": "test_label"})
    
    def test_deserialization(self):
        """Test deserialization from dict."""
        entry_dict = {
            "id": "test456",
            "content": "Deserialization test",
            "kind": "email",
            "tags": ["test", "email"],
            "ts": "2025-06-02T14:45:00",
            "source": "user",
            "meta": {"email_id": "123abc", "subject": "Test Email"}
        }
        
        # Create from dict
        entry = MemoryEntry.from_dict(entry_dict)
        
        # Check values
        self.assertEqual(entry.id, "test456")
        self.assertEqual(entry.content, "Deserialization test")
        self.assertEqual(entry.kind, MemoryKind.EMAIL)
        self.assertEqual(entry.tags, ["test", "email"])
        self.assertEqual(entry.ts.year, 2025)
        self.assertEqual(entry.ts.month, 6)
        self.assertEqual(entry.ts.day, 2)
        self.assertEqual(entry.source, MemorySource.USER)
        self.assertEqual(entry.meta["email_id"], "123abc")
    
    def test_string_enum_conversion(self):
        """Test handling of string values for enums."""
        # Create with string values
        entry = MemoryEntry(
            content="String enum test",
            kind="note",
            source="system"
        )
        
        # Check conversion to enums
        self.assertEqual(entry.kind, MemoryKind.NOTE)
        self.assertEqual(entry.source, MemorySource.SYSTEM)
        
        # Test invalid enum value (should keep as string)
        entry = MemoryEntry(
            content="Invalid enum test",
            kind="invalid_kind",
            source="invalid_source"
        )
        
        # Should keep strings as is
        self.assertEqual(entry.kind, "invalid_kind")
        self.assertEqual(entry.source, "invalid_source")
    
    def test_legacy_preference_conversion(self):
        """Test conversion from legacy preference format."""
        legacy_pref = {
            "id": "legacy123",
            "type": "preference",
            "label": "dark_mode",
            "content": "I prefer dark mode for all interfaces",
            "source": "user",
            "date_added": "2025-05-15T10:15:00",
            "tags": ["user-preference", "dark_mode"]
        }
        
        # Convert from legacy format
        entry = MemoryEntry.from_legacy_preference(legacy_pref)
        
        # Check values
        self.assertEqual(entry.id, "legacy123")
        self.assertEqual(entry.content, "I prefer dark mode for all interfaces")
        self.assertEqual(entry.kind, MemoryKind.PREFERENCE)
        self.assertEqual(entry.tags, ["user-preference", "dark_mode"])
        self.assertEqual(entry.source, MemorySource.USER)
        self.assertEqual(entry.ts.year, 2025)
        self.assertEqual(entry.ts.month, 5)
        self.assertEqual(entry.ts.day, 15)
        self.assertEqual(entry.meta["label"], "dark_mode")
        self.assertEqual(entry.meta["original_format"], "legacy")
    
    def test_legacy_email_conversion(self):
        """Test conversion from legacy email memory format."""
        legacy_email = {
            "email_id": "msg123",
            "subject": "Test Email Subject",
            "sender": "sender@example.com",
            "recipient": "recipient@example.com",
            "date": "2025-05-20T09:30:00",
            "summary": "This is a test email summary",
            "client": "Test Client",
            "tags": ["important", "client_email"],
            "requires_action": True,
            "action_type": "reply",
            "added_date": "2025-05-20T10:00:00"
        }
        
        # Convert from legacy format
        entry = MemoryEntry.from_legacy_email(legacy_email)
        
        # Check values
        self.assertEqual(entry.content, "This is a test email summary")
        self.assertEqual(entry.kind, MemoryKind.EMAIL)
        self.assertIn("important", entry.tags)
        self.assertIn("client_email", entry.tags)
        self.assertIn("action_required", entry.tags)
        self.assertEqual(entry.source, MemorySource.SYSTEM)
        self.assertEqual(entry.ts.year, 2025)
        self.assertEqual(entry.ts.month, 5)
        self.assertEqual(entry.ts.day, 20)
        self.assertEqual(entry.meta["email_id"], "msg123")
        self.assertEqual(entry.meta["subject"], "Test Email Subject")
        self.assertEqual(entry.meta["client"], "Test Client")
        self.assertEqual(entry.meta["action_type"], "reply")
        self.assertEqual(entry.meta["original_format"], "legacy")


if __name__ == "__main__":
    unittest.main()
