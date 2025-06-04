#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Preference detector module for Gmail Chatbot

Detects when users express preferences in their messages and automatically
stores them in the memory system without requiring explicit commands.
"""

import logging
from typing import Tuple, Optional

# Import query classifier
from gmail_chatbot.query_classifier import classify_query_type

# Import memory system
from gmail_chatbot.enhanced_memory import EnhancedMemoryStore

# Set up logging
logger = logging.getLogger(__name__)


class PreferenceDetector:
    """Detects and extracts user preferences from messages.
    
    Uses the ML query classifier to identify when messages contain preference statements,
    then stores these preferences in the memory system for future reference.
    """
    
    def __init__(self, memory_store: EnhancedMemoryStore, confidence_threshold: float = 0.8):
        """Initialize the preference detector.
        
        Args:
            confidence_threshold: Minimum confidence score to automatically store preferences
        """
        self.memory_store = memory_store
        self.confidence_threshold = confidence_threshold
        logger.info(f"Preference detector initialized with threshold {confidence_threshold}")
    
    def process_message(self, message: str) -> Tuple[bool, Optional[str]]:
        """Process a user message to detect and store preferences.
        
        Args:
            message: The user's message text
            
        Returns:
            Tuple of (preference_detected, feedback_message)
            where feedback_message is None if no preference was detected or
            a confirmation message if a preference was stored
        """
        # Skip very short messages
        if len(message.strip()) < 5:
            return False, None
        
        # Classify the message
        classification, confidence, scores = classify_query_type(message)
        
        # Check if it's a preference update
        if classification == "preference_update" and confidence >= self.confidence_threshold:
            # Store the preference
            label = self._extract_preference_label(message)
            self.memory_store.remember_user_preference(message, label=label)
            
            # Generate feedback message
            return True, f"📓 Noted! I've saved your preference about {label if label else 'this topic'}." 
        
        return False, None
    
    def _extract_preference_label(self, message: str) -> str:
        """Extract a label for the preference from the message.
        
        This is a simple heuristic to categorize the preference.
        For a more sophisticated approach, additional NLP would be needed.
        
        Args:
            message: The user's message text
            
        Returns:
            A label for the preference
        """
        message_lower = message.lower()
        
        # Simple keyword matching for common preference categories
        categories = {
            "communication": ["communicate", "notification", "contact", "message", "email", "call", "text"],
            "ui": ["dark mode", "light mode", "theme", "color", "display", "interface"],
            "scheduling": ["schedule", "meeting", "calendar", "availability", "time"],
            "format": ["format", "bullet", "paragraph", "style", "layout"],
            "workflow": ["workflow", "process", "steps", "procedure"],
            "privacy": ["privacy", "share", "data", "personal"],
        }
        
        for category, keywords in categories.items():
            if any(keyword in message_lower for keyword in keywords):
                return category
        
        # Default label
        return "general_preference"

