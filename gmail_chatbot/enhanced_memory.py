#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import time
import random # Added for jitter in retry logic
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from datetime import datetime

# Import the memory models and disk store
from gmail_chatbot.memory_models import MemoryEntry, MemoryKind, MemorySource
from gmail_chatbot.disk_store import DiskStore, DiskStoreError

# Import constants

# Import vector database if available
try:
    from gmail_chatbot.email_vector_db import vector_db, VECTOR_LIBS_AVAILABLE
except ImportError:
    VECTOR_LIBS_AVAILABLE = False
    vector_db = None

# Set up logging
logger = logging.getLogger(__name__)


class EnhancedMemoryStore:
    """Thread-safe persistent memory system for the Gmail chatbot.
    
    This class provides a robust storage system for email metadata, user preferences,
    and interaction history using file locking to prevent data corruption.
    
    Features:
    - Thread-safe file operations with automatic retries
    - Unified memory entry model for all types of data
    - Vector database integration for semantic search (when available)
    - Backward compatibility with legacy memory formats
    """
    
    def __init__(self, memory_path: Optional[Path] = None, schema_version: int = 1):
        """Initialize enhanced memory store with vector-first approach.
        
        Args:
            memory_path: Path to the memory directory
            schema_version: Schema version for memory files
        """
        # Set up memory paths
        self.memory_path = memory_path or Path(__file__).parent / "data" / "memory"
        self.memory_path.mkdir(parents=True, exist_ok=True)
        
        # Define memory file paths
        self.client_memory_path = self.memory_path / "client_memory.json"
        self.email_memory_path = self.memory_path / "email_memory.json"
        self.interaction_memory_path = self.memory_path / "interaction_memory.json"
        self.preferences_path = self.memory_path / "preferences.json"
        self.memory_entries_path = self.memory_path / "memory_entries.json"
        
        # Schema version for serialization
        self.schema_version = schema_version
        
        # Create DiskStore instances for each memory file
        self.client_store = DiskStore(self.client_memory_path, schema_version=schema_version)
        self.email_store = DiskStore(self.email_memory_path, schema_version=schema_version)
        self.interaction_store = DiskStore(self.interaction_memory_path, schema_version=schema_version)
        self.preferences_store = DiskStore(self.preferences_path, schema_version=schema_version)
        self.memory_entries_store = DiskStore(self.memory_entries_path, schema_version=schema_version)
        
        # Initialize memory stores
        self.client_memory = self._load_client_memory()
        self.email_memory = self._load_email_memory()
        self.interaction_memory = self._load_interaction_memory()
        self.preferences = self._load_preferences()
        self.memory_entries = self._load_memory_entries()
        
        # Initialize vector database tracking
        self.indexed_entries = {}
        
        # Check vector database availability
        self.vector_search_available = VECTOR_LIBS_AVAILABLE and vector_db is not None
        if self.vector_search_available:
            logger.info("Vector search is available and enabled")
        else:
            logger.warning("Vector search is not available, falling back to keyword search")
    
    def _load_preferences(self) -> List[Dict[str, Any]]:
        """Load preferences from file with thread-safe operations."""
        try:
            return self.preferences_store.load()
        except DiskStoreError as e:
            logging.error(f"Error loading preferences: {e}")
            return []

    def _load_memory_entries(self) -> List[Dict[str, Any]]:
        """Load general memory entries from file."""
        try:
            return self.memory_entries_store.load()
        except DiskStoreError as e:
            logging.error(f"Error loading memory entries: {e}")
            return []

    def _save_memory_entries(self) -> None:
        """Persist memory entries to disk."""
        try:
            self.memory_entries_store.save(self.memory_entries)
        except DiskStoreError as e:
            logging.error(f"Error saving memory entries: {e}")

    def add_memory_entry(self, entry: Dict[str, Any]) -> bool:
        """Append a general memory entry to the store."""
        try:
            self.memory_entries_store.append(entry)
            self.memory_entries = self.memory_entries_store.load()
            return True
        except DiskStoreError as e:
            logger.error(f"Error adding memory entry: {e}")
            return False
    
    def add_email_memory(self, entry: Union[Dict[str, Any], 'MemoryEntry']) -> None:
        """Add an email memory entry and embed it for vector search.
        
        Args:
            entry: Email memory entry to add (dict or MemoryEntry object)
        """
        # Convert to MemoryEntry if needed
        if not isinstance(entry, MemoryEntry):
            if 'email_id' in entry:
                # Convert from legacy format
                entry = MemoryEntry.from_legacy_email(entry)
            else:
                # Already in new format but as dict
                entry = MemoryEntry.from_dict(entry)
        
        # Attempt to append with more aggressive retries for concurrency
        max_retries = 10  # Increased for better handling of concurrent access
        retry_count = 0
        backoff_time = 0.05  # Start with smaller backoff
        max_backoff = 1.0   # Cap backoff time
        jitter_factor = 0.2  # Add randomness to avoid retry collision
        
        logger.info(f"Adding email memory: {entry.meta.get('subject', 'Unknown')[:30]}...")
        
        while retry_count < max_retries:
            try:
                # Use the atomic append operation provided by DiskStore
                self.email_store.append(entry.to_dict())
                self.email_memory = self.email_store.load()
                logger.info(f"Successfully added email memory for: {entry.meta.get('subject', 'Unknown')[:30]}... on attempt {retry_count+1}")
                break
            except DiskStoreError as e:
                retry_count += 1
                logger.warning(f"Email memory append failed (attempt {retry_count}/{max_retries}): {e}")
                
                if retry_count >= max_retries:
                    logger.error(f"Failed to append email memory after {max_retries} attempts, trying fallback")
                    
                    # Fallback: load latest, append, and save with aggressive locking
                    try:
                        # Use a more aggressive locking approach for fallback
                        self.email_store._acquire_lock()
                        try:
                            # Direct file operations with lock held
                            current_emails = []
                            if self.email_store.path.exists():
                                with open(self.email_store.path, 'r', encoding='utf-8') as f:
                                    current_emails = json.load(f)
                                    
                            # Make sure it's a list
                            if not isinstance(current_emails, list):
                                current_emails = []
                                
                            # Add our entry
                            current_emails.append(entry.to_dict())
                            
                            # Write directly with lock held
                            self.email_store.path.parent.mkdir(exist_ok=True, parents=True)
                            with open(self.email_store.path, 'w', encoding='utf-8') as f:
                                json.dump(current_emails, f, indent=2)
                                
                            # Update our local cache
                            self.email_memory = current_emails
                            logger.info("Successfully saved email memory using fallback direct write method")
                        finally:
                            # Always release lock
                            self.email_store._release_lock()
                    except Exception as fallback_error:
                        logger.error(f"All email memory save methods failed: {fallback_error}")
                        raise DiskStoreError(f"Could not save email memory: {fallback_error}") from fallback_error
                else:
                    # Exponential backoff with jitter to avoid thundering herd
                    sleep_time = min(
                        max_backoff,
                        backoff_time * (2 ** (retry_count - 1)) * (1 + jitter_factor * random.random())
                    )
                    logger.info(f"Retrying email memory append in {sleep_time:.2f}s")
                    time.sleep(sleep_time)
        
        # Add to vector store if available (only if vector_db exists and is initialized)
        if self.vector_search_available and vector_db is not None:
            try:
                self._append_email_memory(entry)
            except Exception as e:
                logger.warning(f"Failed to add email memory to vector DB: {e}")

    def _append_email_memory(self, entry: MemoryEntry) -> None:
        """Validate and add an email entry to the vector database."""
        required = {
            'subject': entry.meta.get('subject'),
            'sender': entry.meta.get('sender'),
            'recipient': entry.meta.get('recipient'),
            'body': entry.content,
            'date': entry.meta.get('date') or (entry.ts.isoformat() if isinstance(entry.ts, datetime) else entry.ts)
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"Missing required field(s) for vector DB: {', '.join(missing)}")

        tags = entry.tags or []
        doc_metadata = {
            'kind': entry.kind.value if isinstance(entry.kind, MemoryKind) else entry.kind
        }
        if entry.meta:
            doc_metadata.update(entry.meta)

        vector_db.add_email(
            email_id=entry.id,
            subject=required['subject'],
            sender=required['sender'],
            recipient=required['recipient'],
            body=required['body'],
            date=required['date'],
            tags=tags,
            metadata=doc_metadata
        )
    
    def _save_email_memory(self) -> None:
        """Save email memory to file with thread-safe operations."""
        try:
            self.email_store.save(self.email_memory)
        except DiskStoreError as e:
            logging.error(f"Error saving email memory: {e}")
    
    def _load_interaction_memory(self) -> List[Dict[str, Any]]:
        """Load interaction memory from file with thread-safe operations."""
        try:
            return self.interaction_store.load()
        except DiskStoreError as e:
            logging.error(f"Error loading interaction memory: {e}")
            return []
    
    def _save_interaction_memory(self) -> None:
        """Save interaction memory to file with thread-safe operations."""
        try:
            self.interaction_store.save(self.interaction_memory)
        except DiskStoreError as e:
            logging.error(f"Error saving interaction memory: {e}")
    
    def _load_client_memory(self) -> Dict[str, Any]:
        """Load client memory from file with thread-safe operations."""
        try:
            return self.client_store.load()
        except DiskStoreError as e:
            logging.error(f"Error loading client memory: {e}")
            return {}
    
    def _save_client_memory(self) -> None:
        """Save client memory to file with thread-safe operations."""
        try:
            self.client_store.save(self.client_memory)
        except DiskStoreError as e:
            logging.error(f"Error saving client memory: {e}")
    
    def _load_email_memory(self) -> List[Dict[str, Any]]:
        """Load email memory from file with thread-safe operations."""
        try:
            return self.email_store.load()
        except DiskStoreError as e:
            logging.error(f"Error loading email memory: {e}")
            return []
            
    def add_client_info(self, client_name: str, client_info: Dict[str, Any] = None) -> None:
        """Add or update client information.
        
        Args:
            client_name: Name of the client
            client_info: Dictionary of client info to update/add
        """
        now = datetime.now().isoformat()
        
        # Load the latest client memory to avoid overwriting concurrent changes
        try:
            self.client_memory = self.client_store.load()
        except DiskStoreError as e:
            logging.warning(f"Failed to reload client memory before update: {e}")
        
        if client_name not in self.client_memory:
            # New client
            self.client_memory[client_name] = {
                "first_seen": now,
                "interactions": 0,
                "info": client_info or {}
            }
            logging.info(f"Added new client: {client_name}")
        else:
            # Update existing client
            if client_info:
                if "info" not in self.client_memory[client_name]:
                    self.client_memory[client_name]["info"] = {}
                # Update info dict
                self.client_memory[client_name]["info"].update(client_info)
            # Update interaction count
            if "interactions" in self.client_memory[client_name]:
                self.client_memory[client_name]["interactions"] += 1
            else:
                self.client_memory[client_name]["interactions"] = 1
            
            logging.info(f"Updated client info: {client_name}")
        
        # Save to disk with thread-safe operations
        try:
            self.client_store.update(client_name, self.client_memory[client_name])
        except DiskStoreError as e:
            logging.error(f"Error using update for client {client_name}: {e}")
            # Fallback to full save
            self._save_client_memory()
    
    def get_client_names(self) -> List[str]:
        """Get a list of all client names in memory.
        
        Returns:
            List of client names
        """
        return list(self.client_memory.keys())
        
    def remember_user_preference(self, content: str, label: Optional[str] = None,
                            source: str = "user", tags: Optional[List[str]] = None) -> None:
        """Record a user preference with thread-safe operations.
        
        Args:
            content: The content of the preference
            label: Optional label for categorizing the preference
            source: Source of the preference (user, system, etc.)
            tags: Optional list of tags
        """
        logger.info(f"Recording user preference: {content[:50]}...")
        
        # Create memory entry
        entry = MemoryEntry(
            kind=MemoryKind.PREFERENCE,
            content=content,
            source=source,
            tags=tags or [],
            meta={
                "label": label or "general_preference",
                "detected_at": datetime.utcnow().isoformat()
            }
        )
        
        # Attempt to append with more aggressive retries for concurrency
        max_retries = 10  # Increased for better handling of concurrent access
        retry_count = 0
        backoff_time = 0.05  # Start with smaller backoff
        max_backoff = 1.0   # Cap backoff time
        jitter_factor = 0.2  # Add randomness to avoid retry collision
        
        while retry_count < max_retries:
            try:
                # Use the atomic append operation provided by DiskStore
                self.preferences_store.append(entry.to_dict())
                self.preferences = self.preferences_store.load()
                logger.info(f"Successfully saved preference: {content[:30]}... on attempt {retry_count+1}")
                break
            except DiskStoreError as e:
                retry_count += 1
                logger.warning(f"Preference append failed (attempt {retry_count}/{max_retries}): {e}")
                
                if retry_count >= max_retries:
                    logger.error(f"Failed to append preference after {max_retries} attempts, trying fallback")
                    
                    # Fallback: load latest, append, and save with aggressive locking
                    try:
                        # Use a more aggressive locking approach for fallback
                        self.preferences_store._acquire_lock()
                        try:
                            current_prefs = []
                            if self.preferences_store.path.exists():
                                with open(self.preferences_store.path, 'r', encoding='utf-8') as f:
                                    current_prefs = json.load(f)
                                    
                            # Make sure it's a list
                            if not isinstance(current_prefs, list):
                                current_prefs = []
                                
                            # Add our entry
                            current_prefs.append(entry.to_dict())
                            
                            # Write directly with lock held
                            self.preferences_store.path.parent.mkdir(exist_ok=True, parents=True)
                            with open(self.preferences_store.path, 'w', encoding='utf-8') as f:
                                json.dump(current_prefs, f, indent=2)
                                
                            # Update our local cache
                            self.preferences = current_prefs
                            logger.info("Successfully saved preference using fallback direct write method")
                        finally:
                            # Always release lock
                            self.preferences_store._release_lock()
                    except Exception as fallback_error:
                        logger.error(f"All preference save methods failed: {fallback_error}")
                        raise fallback_error
                else:
                    # Exponential backoff with jitter to avoid thundering herd
                    sleep_time = min(
                        max_backoff,
                        backoff_time * (2 ** (retry_count - 1)) * (1 + jitter_factor * random.random())
                    )
                    logger.info(f"Retrying preference append in {sleep_time:.2f}s")
                    time.sleep(sleep_time)
                    
        # Add to vector db if available
        if self.vector_search_available and vector_db is not None:
            try:
                # TODO: EmailVectorDB is specialized for emails. Adding preferences here might not be appropriate
                # or would require adapting preference data to fit the email schema.
                # For now, we are not adding preferences to EmailVectorDB.
                # vector_db.add_memory(entry, 'preference')
                logger.info(f"Preference '{entry.content[:30]}...' not added to EmailVectorDB (email-specific store). ")
            except Exception as ve:
                logger.warning(f"Failed to add preference to vector db: {ve}")
                # Continue without vector DB - it's not critical

    def save_note_from_text(self, content: str,
                            tags: Optional[List[str]] = None) -> bool:
        """Save a plain text note in ``memory_entries`` via ``add_memory_entry``.

        Parameters
        ----------
        content:
            The note text to store.
        tags:
            Optional list of tags for the note.

        Returns
        -------
        bool
            ``True`` if the note was saved successfully, ``False`` otherwise.
        """
        logger.info("Saving note from text: %s", content[:50])

        entry = MemoryEntry(
            kind=MemoryKind.NOTE,
            content=content,
            source=MemorySource.USER,
            tags=tags or [],
        ).to_dict()

        # ``add_memory_entry`` already handles exceptions and returns ``bool``
        return self.add_memory_entry(entry)
    
    def add_interaction_memory(self, content: str, tags: Optional[List[str]] = None, 
                                meta: Optional[Dict[str, Any]] = None) -> None:
        """Add a chat interaction memory with thread-safe operations.
        
        Args:
            content: The interaction content
            tags: Optional list of tags
            meta: Optional metadata dict
        """
        logger.info(f"Adding interaction memory: {content[:50]}...")
        
        # Create a new MemoryEntry for the interaction
        entry = MemoryEntry(
            content=content,
            kind="interaction",  # Use string 'interaction' as expected by tests
            source=MemorySource.SYSTEM,
            tags=tags or [],
            meta=meta or {}
        )
        
        # Attempt to append with more aggressive retries for concurrency
        max_retries = 10  # Increased for better handling of concurrent access
        retry_count = 0
        backoff_time = 0.05  # Start with smaller backoff
        max_backoff = 1.0   # Cap backoff time
        jitter_factor = 0.2  # Add randomness to avoid retry collision
        
        while retry_count < max_retries:
            try:
                # Use the atomic append operation provided by DiskStore
                self.interaction_store.append(entry.to_dict())
                self.interaction_memory = self.interaction_store.load()
                logger.info(f"Successfully added interaction memory: {content[:30]}... on attempt {retry_count+1}")
                break
            except DiskStoreError as e:
                retry_count += 1
                logger.warning(f"Interaction memory append failed (attempt {retry_count}/{max_retries}): {e}")
                
                if retry_count >= max_retries:
                    logger.error(f"Failed to append interaction after {max_retries} attempts, trying fallback")
                    
                    # Fallback: load latest, append, and save with aggressive locking
                    try:
                        # Use a more aggressive locking approach for fallback
                        self.interaction_store._acquire_lock()
                        try:
                            # Direct file operations with lock held
                            current_interactions = []
                            if self.interaction_store.path.exists():
                                with open(self.interaction_store.path, 'r', encoding='utf-8') as f:
                                    current_interactions = json.load(f)
                                    
                            # Make sure it's a list
                            if not isinstance(current_interactions, list):
                                current_interactions = []
                                
                            # Add our entry
                            current_interactions.append(entry.to_dict())
                            
                            # Write directly with lock held
                            self.interaction_store.path.parent.mkdir(exist_ok=True, parents=True)
                            with open(self.interaction_store.path, 'w', encoding='utf-8') as f:
                                json.dump(current_interactions, f, indent=2)
                                
                            # Update our local cache
                            self.interaction_memory = current_interactions
                            logger.info("Successfully saved interaction using fallback direct write method")
                        finally:
                            # Always release lock
                            self.interaction_store._release_lock()
                    except Exception as fallback_error:
                        logger.error(f"All interaction save methods failed: {fallback_error}")
                        raise fallback_error
                else:
                    # Exponential backoff with jitter to avoid thundering herd
                    sleep_time = min(
                        max_backoff,
                        backoff_time * (2 ** (retry_count - 1)) * (1 + jitter_factor * random.random())
                    )
                    logger.info(f"Retrying interaction append in {sleep_time:.2f}s")
                    time.sleep(sleep_time)
                    
        # Add to vector db if available
        if self.vector_search_available and vector_db is not None:
            try:
                # TODO: EmailVectorDB is specialized for emails. Adding general interactions here might not be appropriate.
                # For now, we are not adding interactions to EmailVectorDB.
                # vector_db.add_memory(entry, 'interaction')
                logger.info(f"Interaction '{entry.content[:30]}...' not added to EmailVectorDB (email-specific store). ")
            except Exception as ve:
                logger.warning(f"Failed to add interaction to vector db: {ve}")
                # Continue without vector DB - it's not critical
    

    
    def search_memory(self, query: str, kind: Optional[Union[MemoryKind, str]] = None, 
                      limit: int = 5) -> List[Dict[str, Any]]:
        """Search memory for relevant entries using vector search if available.
        
        Args:
            query: The search query
            kind: Optional kind of memory to search (email, preference, etc.)
            limit: Maximum number of results to return
            
        Returns:
            List of matching memory entries as dictionaries
        """
        results = []
        
        # Use vector search if available
        if self.vector_search_available and vector_db is not None:
            try:
                # Convert kind to string if it's an enum
                kind_str = None
                if kind is not None:
                    kind_str = kind if isinstance(kind, str) else kind.value
                
                # Search vector database using the correct EmailVectorDB method
                # EmailVectorDB.search returns List[Tuple[str, float, Dict[str, Any]]]: (doc_id, score, metadata)
                active_metadata_filter = None
                if kind_str:
                    active_metadata_filter = {"kind": kind_str}
                
                vector_search_results = vector_db.search(
                    query_text=query,
                    top_n=limit,
                    metadata_filter=active_metadata_filter
                )
                
                # Convert results to memory entries
                # vector_search_results is a list of (doc_id, score, metadata_dict)
                for doc_id, score, meta in vector_search_results:
                    # The 'id' and 'kind' should be in the metadata_dict if stored correctly by add_email
                    entry_kind = meta.get("kind")
                    original_id = meta.get("id", doc_id) # Use doc_id as fallback if 'id' not in meta

                    if not original_id:
                        logger.warning(f"Skipping vector search result with no ID: {meta}")
                        continue
                    
                    # Reconstruct or find the original entry based on its kind and ID
                    # This part needs to align with how entries are stored locally (self.preferences, self.email_memory, etc.)
                    # self.email_memory is a list of dicts, self.preferences is a list of dicts (MemoryEntry.to_dict())
                    # self.interaction_memory is a list of dicts

                    found_entry = None
                    if entry_kind == (MemoryKind.PREFERENCE.value if isinstance(MemoryKind.PREFERENCE, MemoryKind) else "preference"):
                        for pref_dict in self.preferences:
                            if pref_dict.get('id') == original_id:
                                found_entry = pref_dict
                                break
                    elif entry_kind == (MemoryKind.EMAIL.value if isinstance(MemoryKind.EMAIL, MemoryKind) else "email"):
                        for email_dict in self.email_memory: # email_memory is List[Dict]
                            if email_dict.get('id') == original_id:
                                found_entry = email_dict
                                break
                    elif entry_kind == (MemoryKind.NOTE.value if isinstance(MemoryKind.NOTE, MemoryKind) else "interaction") or entry_kind == "interaction": # Assuming 'interaction' is stored as kind 'note' or 'interaction'
                        for interaction_dict in self.interaction_memory:
                            if interaction_dict.get('id') == original_id:
                                found_entry = interaction_dict
                                break
                    else:
                        logger.warning(f"Unknown kind '{entry_kind}' from vector search result for ID {original_id}")

                    if found_entry:
                        # Ensure we don't add duplicates if keyword search also runs
                        if not any(res.get('id') == original_id for res in results):
                            results.append(found_entry)
                        if len(results) >= limit: # Check limit after adding
                            break # Break from processing vector_search_results
                if len(results) >= limit: # if limit reached, skip keyword search below
                    return results
                
            except Exception as e:
                logger.warning(f"Vector search failed: {str(e)}. Falling back to keyword search.")
                # Fall back to keyword search
        
        # If no results or vector search not available, use keyword search
        if not results:
            results = self._keyword_search(query, kind, limit)
            
        return results
    
    def _keyword_search(self, query: str, kind: Optional[Union[MemoryKind, str]] = None, 
                        limit: int = 5) -> List[Dict[str, Any]]:
        """Search memory using simple keyword matching.
        
        Args:
            query: The search query
            kind: Optional kind of memory to search
            limit: Maximum number of results to return
            
        Returns:
            List of matching memory entries as dictionaries
        """
        results = []
        search_terms = query.lower().split()
        
        # Search preferences
        if kind is None or kind == MemoryKind.PREFERENCE or (isinstance(kind, str) and kind == "preference"):
            for pref in self.preferences:
                # Handle both dictionary and MemoryEntry objects
                if isinstance(pref, dict):
                    content = pref.get("content", "")
                    if any(term in content.lower() for term in search_terms):
                        results.append(pref)
                        if len(results) >= limit:
                            return results
                else:
                    # Assuming it's a MemoryEntry object or has a content attribute
                    try:
                        if hasattr(pref, 'content'):
                            if any(term in pref.content.lower() for term in search_terms):
                                results.append(pref.to_dict() if hasattr(pref, 'to_dict') else pref)
                                if len(results) >= limit:
                                    return results
                    except AttributeError:
                        logger.warning(f"Skipping preference item that is not a dict or MemoryEntry: {type(pref)}")
        
        # Search email memory
        if kind is None or kind == MemoryKind.EMAIL or (isinstance(kind, str) and kind == "email"):
            # Handle email memory which could be a dict of entries or a list
            if isinstance(self.email_memory, dict):
                for _, email_data in self.email_memory.items():
                    # Get content from various fields
                    email_content = ""
                    for field in ["content", "summary", "subject"]:
                        if isinstance(email_data, dict) and field in email_data:
                            email_content += " " + str(email_data[field])
                    
                    if any(term in email_content.lower() for term in search_terms):
                        results.append(email_data)
                        if len(results) >= limit:
                            return results
            elif isinstance(self.email_memory, list):
                for email_data in self.email_memory:
                    # Similar processing for list-based storage
                    if isinstance(email_data, dict):
                        email_content = ""
                        for field in ["content", "summary", "subject"]:
                            if field in email_data:
                                email_content += " " + str(email_data[field])
                        
                        if any(term in email_content.lower() for term in search_terms):
                            results.append(email_data)
                            if len(results) >= limit:
                                return results
        
        # Search interaction memory
        if kind is None or kind == MemoryKind.NOTE or (isinstance(kind, str) and kind in ("note", "interaction")):
            # Handle interaction memory which could be a dict of entries or a list
            if isinstance(self.interaction_memory, dict):
                for _, interaction_data in self.interaction_memory.items():
                    interaction_content = ""
                    for field in ["content", "response", "query"]:
                        if isinstance(interaction_data, dict) and field in interaction_data:
                            interaction_content += " " + str(interaction_data[field])
                    
                    if any(term in interaction_content.lower() for term in search_terms):
                        results.append(interaction_data)
                        if len(results) >= limit:
                            return results
            elif isinstance(self.interaction_memory, list):
                for interaction_data in self.interaction_memory:
                    if isinstance(interaction_data, dict):
                        interaction_content = ""
                        for field in ["content", "response", "query"]:
                            if field in interaction_data:
                                interaction_content += " " + str(interaction_data[field])
                        
                        if any(term in interaction_content.lower() for term in search_terms):
                            results.append(interaction_data)
                            if len(results) >= limit:
                                return results
        
        return results

