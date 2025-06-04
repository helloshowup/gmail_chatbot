#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from gmail_chatbot.email_config import DATA_DIR

# Set up logging
logger = logging.getLogger(__name__)


class EmailMemoryStore:
    """A simple vector-like storage system for email contexts and interactions.
    
    This class provides persistent memory capabilities for the Gmail chatbot by:
    1. Storing email metadata, summaries, and interaction records
    2. Organizing information by client, topic, and date
    3. Retrieving relevant context based on simple semantic matching
    
    This implementation uses JSON files as storage instead of a full vector database
    but provides similar functionality in a lightweight manner.
    """
    
    def __init__(self) -> None:
        """Initialize the email memory storage system."""
        self.memory_dir = DATA_DIR / "memory"
        self.memory_dir.mkdir(exist_ok=True)
        
        # Main memory files
        self.client_memory_file = self.memory_dir / "client_memory.json"
        self.email_memory_file = self.memory_dir / "email_memory.json"
        self.interaction_memory_file = self.memory_dir / "interaction_memory.json"
        
        # Initialize memory stores
        self.client_memory = self._load_or_create(self.client_memory_file)
        self.email_memory = self._load_or_create(self.email_memory_file)
        self.interaction_memory = self._load_or_create(self.interaction_memory_file)
    
    def _load_or_create(self, file_path: Path) -> Dict:
        """Load a memory file or create it if it doesn't exist."""
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.error(f"Error decoding {file_path}. Creating new file.")
                return {}
        else:
            return {}
    
    def _save_memory(self, memory_data: Dict, file_path: Path) -> None:
        """Save memory data to a file."""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(memory_data, f, indent=2)
    
    def add_client_info(self, client_name: str, info: Dict[str, Any]) -> None:
        """Add or update information about a client.
        
        Args:
            client_name: Name of the client
            info: Dictionary of client information to store
        """
        client_key = client_name.lower().replace(' ', '_')
        
        if client_key not in self.client_memory:
            self.client_memory[client_key] = {
                "name": client_name,
                "first_seen": datetime.now().isoformat(),
                "interactions": 0,
                "info": {}
            }
        
        # Update client information
        self.client_memory[client_key]["info"].update(info)
        self.client_memory[client_key]["last_updated"] = datetime.now().isoformat()
        
        # Save to file
        self._save_memory(self.client_memory, self.client_memory_file)
    
    def add_email_memory(self, 
                       email_id: str, 
                       subject: str, 
                       sender: str, 
                       recipient: str,
                       date: str,
                       summary: str,
                       client: Optional[str] = None,
                       tags: Optional[List[str]] = None,
                       requires_action: bool = False,
                       action_type: Optional[str] = None) -> None:
        """Store information about an email for future reference.
        
        Args:
            email_id: Unique identifier for the email
            subject: Email subject
            sender: Email sender
            recipient: Email recipient
            date: Email date
            summary: Summary of email content
            client: Associated client name if applicable
            tags: List of tags/keywords for the email
            requires_action: Whether this email needs action
            action_type: Type of action needed (if applicable)
        """
        if email_id in self.email_memory:
            # Update existing email record
            self.email_memory[email_id].update({
                "last_accessed": datetime.now().isoformat(),
                "summary": summary,  # Update with latest summary
                "requires_action": requires_action,
                "action_type": action_type
            })
            
            # Only update tags if provided
            if tags:
                existing_tags = set(self.email_memory[email_id].get("tags", []))
                updated_tags = list(existing_tags.union(set(tags)))
                self.email_memory[email_id]["tags"] = updated_tags
        else:
            # Create new email record
            self.email_memory[email_id] = {
                "subject": subject,
                "sender": sender,
                "recipient": recipient,
                "date": date,
                "summary": summary,
                "client": client,
                "tags": tags or [],
                "requires_action": requires_action,
                "action_type": action_type,
                "first_seen": datetime.now().isoformat(),
                "last_accessed": datetime.now().isoformat(),
                "access_count": 1
            }
            
            # If this is associated with a client, update client interaction count
            if client and client.lower().replace(' ', '_') in self.client_memory:
                client_key = client.lower().replace(' ', '_')
                self.client_memory[client_key]["interactions"] += 1
                self._save_memory(self.client_memory, self.client_memory_file)
        
        # Save to file
        self._save_memory(self.email_memory, self.email_memory_file)
    
    def record_interaction(self, 
                         query: str, 
                         response: str, 
                         email_ids: Optional[List[str]] = None,
                         client: Optional[str] = None,
                         metadata: Optional[Dict[str, Any]] = None) -> str:
        """Record a user interaction with the chatbot.
        
        Args:
            query: The user's query
            response: The chatbot's response
            email_ids: List of email IDs referenced in this interaction
            client: Associated client if applicable
            metadata: Additional metadata for this interaction
            
        Returns:
            interaction_id: Unique ID for this interaction
        """
        # Generate a unique ID for this interaction
        interaction_id = hashlib.md5(f"{query}:{datetime.now().isoformat()}".encode()).hexdigest()
        
        # Store the interaction
        self.interaction_memory[interaction_id] = {
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "response": response,
            "email_ids": email_ids or [],
            "client": client
        }
        
        # Add metadata if provided
        if metadata:
            self.interaction_memory[interaction_id]["metadata"] = metadata
        
        # Update access count for referenced emails
        if email_ids:
            for email_id in email_ids:
                if email_id in self.email_memory:
                    self.email_memory[email_id]["access_count"] = self.email_memory[email_id].get("access_count", 0) + 1
                    self.email_memory[email_id]["last_accessed"] = datetime.now().isoformat()
            self._save_memory(self.email_memory, self.email_memory_file)
        
        # Save to file
        self._save_memory(self.interaction_memory, self.interaction_memory_file)
        
        return interaction_id
    
    def get_client_context(self, client_name: str) -> Dict[str, Any]:
        """Get context information about a specific client.
        
        Args:
            client_name: Name of the client to get information for
            
        Returns:
            Dictionary of client information and recent interactions
        """
        client_key = client_name.lower().replace(' ', '_')
        
        if client_key not in self.client_memory:
            return {"found": False, "message": f"No information found for client {client_name}"}
        
        # Get client info
        client_info = self.client_memory[client_key]
        
        # Find recent emails related to this client
        client_emails = []
        for email_id, email_data in self.email_memory.items():
            if email_data.get("client") == client_name:
                client_emails.append({
                    "email_id": email_id,
                    "subject": email_data["subject"],
                    "date": email_data["date"],
                    "summary": email_data["summary"],
                    "requires_action": email_data.get("requires_action", False)
                })
        
        # Sort by date (most recent first) and limit to 5
        client_emails.sort(key=lambda x: x["date"], reverse=True)
        recent_emails = client_emails[:5]
        
        return {
            "found": True,
            "client_info": client_info,
            "recent_emails": recent_emails,
            "email_count": len(client_emails),
            "action_required_count": sum(1 for e in client_emails if e.get("requires_action", False))
        }
    
    # Default keyword search weights
    KEYWORD_WEIGHTS = {
        'subject': 3,
        'tags': 2,
        'summary': 1
    }
    
    def find_related_emails(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Find emails related to a specific query using simple keyword matching.
        This is a simplified version of vector search using keyword matching.
        
        Args:
            query: Search query
            max_results: Maximum number of results to return
            
        Returns:
            List of related email information
        """
        # Convert query to lowercase for case-insensitive matching
        query_terms = query.lower().split()
        
        # Calculate relevance scores for each email
        scored_emails = []
        for email_id, email_data in self.email_memory.items():
            score = 0
            
            # Check subject
            subject_lower = email_data["subject"].lower()
            for term in query_terms:
                if term in subject_lower:
                    score += self.KEYWORD_WEIGHTS['subject']
            
            # Check summary
            summary_lower = email_data["summary"].lower()
            for term in query_terms:
                if term in summary_lower:
                    score += self.KEYWORD_WEIGHTS['summary']
            
            # Check tags
            for tag in email_data.get("tags", []):
                for term in query_terms:
                    if term in tag.lower():
                        score += self.KEYWORD_WEIGHTS['tags']
            
            if score > 0:
                scored_emails.append((email_id, email_data, score))
        
        # Sort by score (highest first)
        scored_emails.sort(key=lambda x: x[2], reverse=True)
        
        # Return top results
        results = []
        for email_id, email_data, score in scored_emails[:max_results]:
            results.append({
                "email_id": email_id,
                "subject": email_data["subject"],
                "sender": email_data["sender"],
                "date": email_data["date"],
                "summary": email_data["summary"],
                "client": email_data.get("client"),
                "relevance_score": score,
                "requires_action": email_data.get("requires_action", False)
            })
        
        return results
    
    def get_action_items(self) -> List[Dict[str, Any]]:
        """Get all emails that require action.
        
        Returns:
            List of emails requiring action, sorted by date
        """
        action_items = []
        
        for email_id, email_data in self.email_memory.items():
            if email_data.get("requires_action", False):
                action_items.append({
                    "email_id": email_id,
                    "subject": email_data["subject"],
                    "sender": email_data["sender"],
                    "date": email_data["date"],
                    "summary": email_data["summary"],
                    "client": email_data.get("client"),
                    "action_type": email_data.get("action_type")
                })
        
        # Sort by date (most recent first)
        action_items.sort(key=lambda x: x["date"], reverse=True)
        
        return action_items
    
    def get_client_names(self) -> List[str]:
        """Get list of all known client names."""
        return [data["name"] for _, data in self.client_memory.items()]
    
    def mark_email_handled(self, email_id: str) -> bool:
        """Mark an email as no longer requiring action.
        
        Args:
            email_id: ID of the email to mark as handled
            
        Returns:
            True if successful, False otherwise
        """
        if email_id in self.email_memory:
            self.email_memory[email_id]["requires_action"] = False
            self.email_memory[email_id]["handled_date"] = datetime.now().isoformat()
            self._save_memory(self.email_memory, self.email_memory_file)
            return True
        return False
