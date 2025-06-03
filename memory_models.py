#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Dict, List, Any, Union


class MemoryKind(str, Enum):
    """Types of memory entries supported by the system."""
    EMAIL = "email"
    NOTE = "note"
    PREFERENCE = "preference"
    PROJECT = "project"


class MemorySource(str, Enum):
    """Source of memory entries."""
    USER = "user"
    SYSTEM = "system"
    IMPORT = "import"


@dataclass
class MemoryEntry:
    """Unified data model for all memory entries.
    
    This provides a consistent structure for different types of memory entries
    such as emails, preferences, notes, and project information.
    
    By standardizing the schema, we can apply consistent processing,
    embedding, and retrieval across all memory types.
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    kind: Union[MemoryKind, str] = MemoryKind.NOTE
    content: str = ""
    tags: List[str] = field(default_factory=list)
    ts: datetime = field(default_factory=datetime.utcnow)
    source: Union[MemorySource, str] = MemorySource.USER
    meta: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate and convert attributes after initialization."""
        # Convert string kind to enum if needed
        if isinstance(self.kind, str):
            try:
                self.kind = MemoryKind(self.kind)
            except ValueError:
                # Keep as string if not a valid enum value (for backward compatibility)
                pass
        
        # Convert string source to enum if needed
        if isinstance(self.source, str):
            try:
                self.source = MemorySource(self.source)
            except ValueError:
                # Keep as string if not a valid enum value (for backward compatibility)
                pass
        
        # Convert string timestamp to datetime if needed
        if isinstance(self.ts, str):
            try:
                self.ts = datetime.fromisoformat(self.ts)
            except ValueError:
                # Fallback to current time if parsing fails
                self.ts = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization.
        
        Returns:
            Dictionary representation with properly serialized values
        """
        result = asdict(self)
        
        # Convert enum values to strings
        if isinstance(result['kind'], MemoryKind):
            result['kind'] = result['kind'].value
            
        if isinstance(result['source'], MemorySource):
            result['source'] = result['source'].value
        
        # Convert datetime to ISO format string
        if isinstance(result['ts'], datetime):
            result['ts'] = result['ts'].isoformat()
            
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryEntry':
        """Create a MemoryEntry from a dictionary.
        
        Args:
            data: Dictionary containing memory entry data
            
        Returns:
            New MemoryEntry instance
        """
        # Handle ts field conversion from string to datetime
        if 'ts' in data and isinstance(data['ts'], str):
            try:
                data['ts'] = datetime.fromisoformat(data['ts'])
            except ValueError:
                data['ts'] = datetime.utcnow()
        
        return cls(**data)
    
    @classmethod
    def from_legacy_preference(cls, pref_data: Dict[str, Any]) -> 'MemoryEntry':
        """Convert legacy preference format to MemoryEntry.
        
        Args:
            pref_data: Dictionary in the old preference format
            
        Returns:
            New MemoryEntry with preference data
        """
        return cls(
            id=pref_data.get('id', uuid.uuid4().hex),
            kind=MemoryKind.PREFERENCE,
            content=pref_data.get('content', ''),
            tags=pref_data.get('tags', []),
            ts=datetime.fromisoformat(pref_data.get('date_added', datetime.utcnow().isoformat())),
            source=MemorySource.USER if pref_data.get('source') == 'user' else MemorySource.SYSTEM,
            meta={
                'label': pref_data.get('label', ''),
                'original_format': 'legacy'
            }
        )
    
    @classmethod
    def from_legacy_email(cls, email_data: Dict[str, Any]) -> 'MemoryEntry':
        """Convert legacy email memory format to MemoryEntry.
        
        Args:
            email_data: Dictionary in the old email memory format
            
        Returns:
            New MemoryEntry with email data
        """
        # Extract tags from original data
        tags = email_data.get('tags', [])
        if email_data.get('requires_action', False):
            tags.append('action_required')
            
        # Build the meta field from email-specific attributes
        meta = {
            'email_id': email_data.get('email_id', ''),
            'subject': email_data.get('subject', ''),
            'sender': email_data.get('sender', ''),
            'recipient': email_data.get('recipient', ''),
            'date': email_data.get('date', ''),
            'client': email_data.get('client', None),
            'action_type': email_data.get('action_type', None),
            'original_format': 'legacy'
        }
        
        # Create the memory entry
        return cls(
            id=email_data.get('id', uuid.uuid4().hex),
            kind=MemoryKind.EMAIL,
            content=email_data.get('summary', ''),
            tags=tags,
            ts=datetime.fromisoformat(email_data.get('added_date', datetime.utcnow().isoformat())),
            source=MemorySource.SYSTEM,
            meta=meta
        )
