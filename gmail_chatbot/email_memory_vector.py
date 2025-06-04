#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import hashlib
from typing import Dict, List, Any, Optional
from datetime import datetime

# Import the base memory store for backward compatibility
from gmail_chatbot.email_memory import EmailMemoryStore

# Import the vector database
from gmail_chatbot.email_vector_db import vector_db

# Set up logging
logger = logging.getLogger(__name__)


class EmailVectorMemoryStore(EmailMemoryStore):
    """
    Enhanced EmailMemoryStore with vector database integration using FAISS.
    
    This extends the basic EmailMemoryStore with semantic search capabilities
    while maintaining backward compatibility with the original implementation.
    
    It integrates with the FAISS vector database for more accurate semantic matching
    and falls back to the original keyword-based search when vector search is not available.
    """
    
    def __init__(self) -> None:
        """Initialize the enhanced vector-based email memory storage system."""
        # Initialize the base memory store
        super().__init__()
        
        # Defensive check to ensure memory_entries and preferences are initialized
        # These are used by the base class or this class for storing preferences/notes.
        if not hasattr(self, 'memory_entries'): # memory_entries might be used by base or for other note types
            self.memory_entries = []
            logger.warning("Initialized missing memory_entries list.")
        if not hasattr(self, 'preferences'): # preferences are checked in is_notebook_empty and get_concise_notebook_summary
            self.preferences = [] # Assuming preferences are stored as a list of dicts or MemoryEntry objects
            logger.warning("Initialized missing preferences list.")
        
        # Initialize vector DB status from the vector_db instance
        self.vector_search_available: bool = vector_db.vector_search_available
        self.vector_search_error_message: Optional[str] = vector_db.initialization_error_message

        if self.vector_search_available:
            logger.info("Vector search is available and enabled.")
        else:
            log_msg = "Vector search is NOT available."
            if self.vector_search_error_message:
                log_msg += f" Reason: {self.vector_search_error_message}"
            else:
                # This case might occur if VECTOR_LIBS_AVAILABLE was false but EmailVectorDB init didn't set a message (should be covered now)
                log_msg += " Reason: Core vector libraries (FAISS, embeddings) might be missing or failed to load."
            logger.warning(log_msg)
            logger.info("Falling back to keyword-based search if applicable.")
            
        # Track emails that have been added to the vector DB
        self.vector_indexed_emails = set()
        self.vector_index_file = self.memory_dir / "vector_indexed_emails.json"
        
        # Load the list of already indexed emails
        self._load_indexed_emails()
    
    def get_vector_search_error_message(self) -> Optional[str]:
        """Return the error message related to vector search initialization, if any."""
        return self.vector_search_error_message

    def _load_indexed_emails(self) -> None:
        """Load the list of emails that have been indexed in the vector database."""
        if self.vector_index_file.exists():
            try:
                with open(self.vector_index_file, 'r', encoding='utf-8') as f:
                    self.vector_indexed_emails = set(json.load(f))
                logger.info(f"Loaded {len(self.vector_indexed_emails)} indexed email IDs")
            except Exception as e:
                logger.error(f"Error loading vector indexed emails: {e}")
                self.vector_indexed_emails = set()
    
    def _save_indexed_emails(self) -> None:
        """Save the list of emails that have been indexed in the vector database."""
        try:
            with open(self.vector_index_file, 'w', encoding='utf-8') as f:
                json.dump(list(self.vector_indexed_emails), f)
        except Exception as e:
            logger.error(f"Error saving vector indexed emails: {e}")
    
    def add_email_memory(self, 
                        email_id: str, 
                        subject: str, 
                        sender: str, 
                        recipient: str,
                        date: str,
                        summary: str,
                        body: Optional[str] = None,  # Added parameter for the full email body
                        client: Optional[str] = None,
                        tags: Optional[List[str]] = None,
                        requires_action: bool = False,
                        action_type: Optional[str] = None) -> None:
        """Store information about an email and index in vector database if possible.
        
        Args:
            email_id: Unique identifier for the email
            subject: Email subject
            sender: Email sender
            recipient: Email recipient
            date: Email date
            summary: Summary of email content
            body: Full email body text for vector indexing (optional)
            client: Associated client name if applicable
            tags: List of tags/keywords for the email
            requires_action: Whether this email needs action
            action_type: Type of action needed (if applicable)
        """
        # First, store in the base memory system
        super().add_email_memory(
            email_id=email_id,
            subject=subject,
            sender=sender,
            recipient=recipient,
            date=date,
            summary=summary,
            client=client,
            tags=tags,
            requires_action=requires_action,
            action_type=action_type
        )
        
        # If vector search is available and we have the body text, add to vector DB
        if self.vector_search_available and body:
            try:
                # Check if this email is already in the vector DB
                if email_id in self.vector_indexed_emails:
                    # Check if we need to reindex (e.g., if the content has changed)
                    current_email = self.email_memory.get(email_id, {})
                    content_changed = current_email.get("summary") != summary
                    
                    if content_changed:
                        logger.info(f"Email {email_id} content changed, reindexing in vector DB")
                    else:
                        logger.debug(f"Email {email_id} already indexed in vector DB")
                        return
                
                # Add/update in vector DB
                tags_list = tags or []
                if client:
                    tags_list.append(f"client:{client}")
                
                # Add to vector database
                result = vector_db.add_email(
                    email_id=email_id,
                    subject=subject,
                    sender=sender,
                    recipient=recipient,
                    body=body,  # Use full email body for better vector representation
                    date=date,
                    tags=tags_list,
                    force_reindex=True if email_id in self.vector_indexed_emails else False
                )
                
                if result:
                    # Track that this email has been indexed
                    self.vector_indexed_emails.add(email_id)
                    self._save_indexed_emails()
                    logger.info(f"Email {email_id} successfully indexed in vector DB")
                else:
                    logger.warning(f"Failed to index email {email_id} in vector DB")
                    
            except Exception as e:
                logger.error(f"Error indexing email in vector DB: {e}")
    

    
    def is_notebook_empty(self) -> bool:
        """Check if the notebook (emails, clients, preferences) is empty."""
        # Check emails in vector DB (via vector_indexed_emails for speed) and base email_memory
        # Check client_info and preferences from the base class (EmailMemoryStore)
        # A notebook is empty if no emails are stored, no client info (beyond default), and no preferences (beyond default).
        # self.preferences is initialized in EmailMemoryStore, self.client_memory also.
        # self.email_memory is also from EmailMemoryStore.
        # self.vector_indexed_emails tracks emails in the vector DB part.

        no_emails_in_vector_db = not self.vector_indexed_emails
        no_emails_in_base_memory = not self.email_memory
        no_client_info = not self.client_memory # client_memory is loaded from file in EmailMemoryStore
        no_preferences = not self.preferences # preferences is loaded from file in EmailMemoryStore

        return no_emails_in_vector_db and no_emails_in_base_memory and no_client_info and no_preferences

    def get_concise_notebook_summary(self, max_items_per_category: int = 3) -> str:
        """Generate a concise, data-driven summary of the notebook's contents using markdown.

        Args:
            max_items_per_category: Max number of items to list for emails, clients, preferences.
        """
        if self.is_notebook_empty():
            return "- Your notebook is currently empty. Add emails, notes, or client details to get started!"

        summary_parts = []

        # Email Summary
        # Prioritize emails from email_memory as it might have more structured data like 'summary'
        # Sort emails by 'last_accessed' or 'date' to get recent ones.
        # Assuming email_memory stores dicts with 'date' or 'last_accessed' and 'subject'/'summary'.
        emails_to_summarize = []
        if self.email_memory:
            try:
                # Attempt to sort by date, falling back if date format is inconsistent or missing
                sorted_email_ids = sorted(
                    self.email_memory.keys(),
                    key=lambda eid: self.email_memory[eid].get('last_accessed', self.email_memory[eid].get('date', '1970-01-01T00:00:00Z')),
                    reverse=True
                )
            except Exception as e:
                logger.warning(f"Could not sort emails for summary due to: {e}. Using unsorted emails.")
                sorted_email_ids = list(self.email_memory.keys())
            
            for email_id in sorted_email_ids[:max_items_per_category]:
                email_data = self.email_memory[email_id]
                email_desc = email_data.get('subject', 'Email with no subject')
                if email_data.get('summary'):
                    email_desc += f" (Summary: {email_data['summary'][:50]}...)"
                emails_to_summarize.append(email_desc)
        
        if emails_to_summarize:
            summary_parts.append("**Recent Email Notes:**")
            for email_item in emails_to_summarize:
                summary_parts.append(f"- {email_item}")
        elif self.vector_indexed_emails or self.email_memory: # If sorted list is empty but emails exist
            summary_parts.append("- Contains notes from email(s).")

        # Client Summary
        if self.client_memory:
            summary_parts.append("**Client Information:**")
            client_names = [data.get('name', key) for key, data in self.client_memory.items()]
            for i, name in enumerate(client_names[:max_items_per_category]):
                summary_parts.append(f"- {name}")
            if len(client_names) > max_items_per_category:
                summary_parts.append(f"- ...and {len(client_names) - max_items_per_category} more client(s).")
        
        # Preferences Summary
        # Assuming self.preferences is a list of dicts or MemoryEntry-like objects with a 'content' field.
        if hasattr(self, 'preferences') and self.preferences:
            summary_parts.append("**User Preferences:**")
            for i, pref_item in enumerate(self.preferences[:max_items_per_category]):
                content = ""
                if isinstance(pref_item, dict):
                    content = pref_item.get('content', 'Recorded preference')
                elif hasattr(pref_item, 'content'): # For MemoryEntry objects
                    content = pref_item.content
                else:
                    content = str(pref_item)
                summary_parts.append(f"- {content[:100]}{'...' if len(content) > 100 else ''}")
            if len(self.preferences) > max_items_per_category:
                summary_parts.append(f"- ...and {len(self.preferences) - max_items_per_category} more preference(s).")

        if not summary_parts: # Should not happen if is_notebook_empty() is false
            return "- The notebook contains some information, but a detailed summary could not be generated."
            
        return "\n".join(summary_parts)

    def get_vector_status(self) -> Dict[str, Any]:
        """Get status information about the vector database.
        
        Returns:
            Dict with status information
        """
        status = {
            "vector_search_available": self.vector_search_available,
            "indexed_emails": len(self.vector_indexed_emails),
            "total_emails": len(self.email_memory)
        }
        
        # Add details from vector DB if available
        if self.vector_search_available:
            vector_status = vector_db.get_status()
            status.update({
                "embedding_model": vector_status.get("embedding_model"),
                "total_chunks": vector_status.get("total_chunks"),
                "cache_dir": vector_status.get("cache_dir")
            })
        
        return status
    
    def find_related_emails(self, query: str, limit: int = 5, 
                      min_relevance: float = 0.0,
                      filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Find emails related to a specific query using vector search if available with filtering options.
        Falls back to keyword matching if vector search is unavailable.
        
        Args:
            query: Search query
            limit: Maximum number of results to return (previously max_results)
            min_relevance: Minimum relevance score (0-10) to include in results
            filters: Optional filters to apply (sender, date_range, etc.)
        
        Returns:
            List of related email information with relevance scores
        """
        # Try vector search first if available
        if self.vector_search_available and len(self.vector_indexed_emails) > 0:
            try:
                logger.info(f"Using vector search for query: {query} (limit={limit}, min_relevance={min_relevance})")
                # Request more results than needed to allow for filtering by min_relevance
                search_limit = min(limit * 2, 20)  # Double the limit but cap at 20 to avoid excessive results
                vector_results = vector_db.search(query, num_results=search_limit, filters=filters)
                
                if vector_results:
                    # Convert vector results to the expected format
                    results = []
                
                for result in vector_results:
                    # Get the email ID from the search result metadata
                    email_id = result['metadata'].get('email_id')
                    
                    # Calculate relevance score (0-10 scale)
                    relevance_score = round(result['similarity'] * 10, 2)  # Round to 2 decimal places for readability
                    
                    # Skip results below minimum relevance threshold
                    if relevance_score < min_relevance:
                        continue
                    
                    # If this email exists in our memory, use the full metadata
                    if email_id in self.email_memory:
                        email_data = self.email_memory[email_id]
                        
                        results.append({
                            "email_id": email_id,
                            "subject": email_data["subject"],
                            "sender": email_data["sender"],
                            "date": email_data["date"],
                            "summary": email_data["summary"],
                            "client": email_data.get("client"),
                            "relevance_score": relevance_score,
                            "requires_action": email_data.get("requires_action", False),
                            "search_type": "vector"
                        })
                    
                    if results:
                        # Sort by relevance score (highest first) and limit to requested number
                        results.sort(key=lambda x: x['relevance_score'], reverse=True)
                        results = results[:limit]
                        
                        logger.info(f"Found {len(results)} related emails using vector search (after relevance filtering)")
                        return results
                    
                logger.info("No vector search results, falling back to keyword search")
            except Exception as e:
                logger.error(f"Error in vector search: {e}")
        
        # Fall back to keyword search
        logger.info(f"Using keyword search for query: {query}")
        keyword_results = super().find_related_emails(query, limit)  # Use updated parameter name
        
        # Add search type to distinguish in logs
        for result in keyword_results:
            result["search_type"] = "keyword"
            
        return keyword_results


    def batch_process_historical_emails(self, limit: int, callback: Optional[callable] = None) -> Dict[str, Any]:
        """Process a batch of historical emails to add to the vector database.
        
        This function indexes emails that are already in the JSON memory but not yet in the vector DB.
        
        Args:
            limit: Maximum number of emails to process
            callback: Optional callback function to update progress
                     Expected signature: callback(progress_pct, processed_count, total_count)
        
        Returns:
            Dict with processing results
        """
        if not self.vector_search_available:
            raise RuntimeError("Vector libraries not available, cannot process batch")
            
        results = {
            "success": False,
            "processed": 0,
            "indexed": 0,
            "errors": 0,
            "skipped": 0,
            "total_emails": len(self.email_memory)
        }
        
        try:
            # Find emails not yet indexed in vector DB
            unindexed_emails = []
            for email_id, email_data in self.email_memory.items():
                if email_id not in self.vector_indexed_emails:
                    unindexed_emails.append((email_id, email_data))
            
            # Limit the number of emails to process
            unindexed_emails = unindexed_emails[:limit]
            total_to_process = len(unindexed_emails)
            
            logger.info(f"Starting batch processing of {total_to_process} unindexed emails")
            results["total_to_process"] = total_to_process
            
            # Process emails
            for i, (email_id, email_data) in enumerate(unindexed_emails):
                try:
                    # Extract email data
                    subject = email_data.get("subject", "")
                    sender = email_data.get("sender", "")
                    recipient = email_data.get("recipient", "")
                    date = email_data.get("date", "")
                    summary = email_data.get("summary", "")
                    client = email_data.get("client")
                    tags = email_data.get("tags", [])
                    
                    # For historical emails, we might not have the full body, so create a synthetic one
                    # combining subject and summary for vector indexing
                    body = f"Subject: {subject}\n\n{summary}"
                    
                    # Add to vector database
                    tags_list = tags or []
                    if client:
                        tags_list.append(f"client:{client}")
                    
                    result = vector_db.add_email(
                        email_id=email_id,
                        subject=subject,
                        sender=sender,
                        recipient=recipient,
                        body=body,
                        date=date,
                        tags=tags_list,
                        force_reindex=False  # This is a first-time indexing
                    )
                    
                    if result:
                        # Track that this email has been indexed
                        self.vector_indexed_emails.add(email_id)
                        results["indexed"] += 1
                        logger.info(f"Batch indexed email {email_id}")
                    else:
                        results["errors"] += 1
                        logger.warning(f"Failed to batch index email {email_id}")
                except Exception as e:
                    results["errors"] += 1
                    logger.error(f"Error batch indexing email {email_id}: {e}")
                
                # Update progress
                results["processed"] += 1
                if callback and callable(callback):
                    progress_pct = (i + 1) / total_to_process * 100
                    callback(progress_pct, i + 1, total_to_process)
            
            # Save the updated indexed emails list
            self._save_indexed_emails()
            
            # Update results
            results["success"] = True
            results["skipped"] = total_to_process - results["indexed"] - results["errors"]
            
            logger.info(f"Batch processing complete: {results['indexed']} indexed, {results['errors']} errors")
            return results
        except Exception as e:
            logger.error(f"Error in batch processing: {e}")
            results["error_message"] = str(e)
            return results
    
    def remember_user_preference(self, label: str, content: str, source: str = "user", tags: List[str] = None) -> bool:
        """Store structured user preferences for later use.
        
        Args:
            label: Category label for the preference (e.g., 'busywork', 'inbox_management')
            content: The content of the preference
            source: Source of the preference ('user', 'user_clarified', etc.)
            tags: Optional list of tags to associate with this preference
            
        Returns:
            bool: True if the preference was successfully stored, False otherwise
        """
        try:
            tags = tags or []
            
            # Check vector availability early and log it
            if not self.vector_search_available:
                logger.warning(f"Vector DB unavailable — storing preference for '{label}' in plain memory only.")
            
            # Create preference entry
            preference_id = hashlib.md5(f"{label}_{content}_{datetime.now().isoformat()}".encode()).hexdigest()
            preference_entry = {
                "id": preference_id,
                "type": "preference",
                "label": label.lower(),
                "content": content,
                "source": source,
                "date_added": datetime.now().isoformat(),
                "tags": tags
            }
            
            # Add to memory entries
            self.memory_entries.append(preference_entry)
            
            # Save to disk
            self._save_memory(self.memory_entries, self.memory_dir / "preferences.json")
            
            logger.info(f"Stored user preference with label: {label}, content: '{content[:50]}...' (truncated)")
            
            # Add to vector DB if available
            if self.vector_search_available:
                try:
                    # Create a rich text representation that includes all metadata
                    text_for_embedding = f"USER PREFERENCE - {label}: {content} (tags: {', '.join(tags)})" 
                    
                    # Add to vector database
                    vector_db.add_text(text_for_embedding, metadata={
                        "id": preference_id,
                        "type": "preference",
                        "label": label.lower(),
                        "date_added": datetime.now().isoformat()
                    })
                    
                    logger.info(f"Added user preference to vector database: {label}")
                except Exception as e:
                    logger.error(f"Error adding preference to vector DB: {e}")
                    # Important: we still return True because the preference was stored in basic memory
                    # This prevents the error message from appearing to the user
            
            return True
        except Exception as e:
            logger.error(f"Error storing user preference: {e}")
            return False
    
    def get_user_preferences(self, label: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve stored user preferences.
        
        Args:
            label: Optional label to filter preferences by category
            
        Returns:
            List of preference entries matching the filter
        """
        return [
            entry for entry in self.memory_entries
            if entry.get("type") == "preference" and 
               (label is None or entry.get("label", "").lower() == label.lower())
        ]
        
    def find_relevant_preferences(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Find preferences relevant to a user query using vector search if available.
        
        Args:
            query: The user's query or context
            limit: Maximum number of preferences to return
            
        Returns:
            List of relevant preference entries
        """
        relevant_prefs = []
        
        # Try vector search first if available
        if self.vector_search_available:
            try:
                # Search for relevant preferences in vector space
                results = vector_db.search_text(query, filter_metadata={"type": "preference"}, limit=limit)
                
                # Convert results to preference entries
                for result in results:
                    pref_id = result.get("metadata", {}).get("id")
                    if pref_id:
                        # Find the original preference in memory entries
                        for entry in self.memory_entries:
                            if entry.get("id") == pref_id and entry.get("type") == "preference":
                                relevant_prefs.append(entry)
                                break
            except Exception as e:
                logger.error(f"Error in vector search for preferences: {e}")
        
        # If vector search failed or isn't available, fall back to keyword matching
        if not relevant_prefs:
            query_terms = query.lower().split()
            
            # Score each preference by keyword matches
            scored_prefs = []
            for pref in self.get_user_preferences():
                score = 0
                pref_text = f"{pref.get('label', '')} {pref.get('content', '')} {' '.join(pref.get('tags', []))}".lower()
                
                for term in query_terms:
                    if term in pref_text:
                        score += 1
                
                if score > 0:
                    scored_prefs.append((score, pref))
            
            # Sort by score and take the top ones
            scored_prefs.sort(reverse=True)
            relevant_prefs = [pref for _, pref in scored_prefs[:limit]]
        
        return relevant_prefs
    
    def get_all_email_ids(self) -> List[str]:
        """Get list of all email IDs stored in memory.
        
        Returns:
            List of email IDs
        """
        return list(self.email_memory.keys())

