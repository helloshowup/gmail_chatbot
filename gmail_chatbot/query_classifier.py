#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Query classifier for the Gmail Chatbot application.
Uses ML model for primary classification with regex patterns as fallback.
Provides confidence scores and detailed probability distribution for all categories.
"""

from typing import List, Dict, Literal, Tuple, Optional, get_args, cast
import logging
import re
import os
from datetime import datetime

# Configure module logger
logger = logging.getLogger(__name__)

# Classification confidence thresholds - single source of truth
THRESHOLDS = {
    # Main confidence threshold for general classification
    'GENERAL': 0.25,
    # Lower threshold for queries that should still be attempted even with low confidence
    'LOOKUP_LENIENT': 0.30,  
    # Absolute minimum threshold below which all queries are treated as ambiguous
    'ABSOLUTE_MIN': 0.25,
    # Confidence value for keyword-based overrides
    'KEYWORD_OVERRIDE': 0.65,
    # Vector search relevance thresholds
    'VECTOR_SEARCH': {
        'HIGH_CONFIDENCE': 0.40,  # Above this confidence, use more results
        'MIN_RELEVANCE': 5.0     # Minimum relevance score to consider reliable
    }
}

# Log thresholds at startup for easy debugging
logger.info(f"Query classifier thresholds: {THRESHOLDS}")

# Import ML classifier class and error type
try:
    # Import from the installed gmail_chatbot package.
    from gmail_chatbot.ml_classifier.ml_query_classifier import MLQueryClassifier, ClassifierError
    _MLQueryClassifier_CLASS_AVAILABLE = True
    logging.info("MLQueryClassifier class successfully imported.")
except (ImportError, ModuleNotFoundError) as e:
    logging.warning(f"Could not import MLQueryClassifier class from ml_classifier.ml_query_classifier: {e}. ML classification will be unavailable.")
    MLQueryClassifier = None  # type: ignore # Define for type hinting and graceful failure
    ClassifierError = Exception  # type: ignore # Define for graceful failure in try-except blocks
    _MLQueryClassifier_CLASS_AVAILABLE = False

# Define query types
# Note: 'general_chat' is explicitly kept in the type definition to match the ML model output
# It gets mapped to 'chat' during classification for UI consistency
QueryType = Literal["email_search", "triage", "catch_up", "clarify", "general_chat", "vector_fallback", "ambiguous", "mixed_semantic", "chat", "notebook_lookup", "preference_update"]


def calculate_pattern_match_scores(query: str, patterns_dict: Dict[str, List[str]]) -> Dict[str, float]:
    """Calculate match scores for each category based on regex patterns and word matching.
    
    Args:
        query: The user's input query
        patterns_dict: Dictionary mapping category names to lists of patterns
        
    Returns:
        Dictionary of category scores (0.0-1.0)
    """
    query_lower = query.lower().strip()
    words = set(re.findall(r'\w+', query_lower))  # Extract words for partial matching
    scores = {}
    
    # Calculate scores for each category
    for category, patterns in patterns_dict.items():
        # Start with 0 score
        score = 0.0
        max_possible = len(patterns)  # Maximum possible matches
        
        # Check each pattern
        for pattern in patterns:
            # Exact phrase match (highest weight)
            if pattern in query_lower:
                score += 1.0
                continue
                
            # Word boundary match (medium weight)
            pattern_words = set(re.findall(r'\w+', pattern))
            if any(word in words for word in pattern_words) and len(pattern_words) > 0:
                score += 0.5 * (sum(1 for word in pattern_words if word in words) / len(pattern_words))
        
        # Normalize score to 0-1 range
        if max_possible > 0:
            scores[category] = min(1.0, score / max_possible)
        else:
            scores[category] = 0.0
            
    return scores

# Precompiled regex patterns for frequently used queries
TELL_ME_ABOUT_PATTERN = re.compile(r"^\s*tell\s+me\s+about\s+(.+)", re.IGNORECASE)
WHO_IS_PATTERN = re.compile(r"^\s*who\s+is\s+(.+)", re.IGNORECASE)
WHAT_IS_PATTERN = re.compile(r"^\s*what\s+(is|are)\s+(.+)", re.IGNORECASE)
INFO_ON_PATTERN = re.compile(
    r"^.*?(information|details|notes)\s+on\s+(.+)", re.IGNORECASE
)
SEARCH_GMAIL_PATTERN = re.compile(
    r"\bsearch\s+gmail\s+for\s+(?P<query>.+)", re.IGNORECASE
)
TODAYS_EMAIL_PATTERN = re.compile(
    r"\b(today'?s|todays)\s+email\b", re.IGNORECASE
)

def classify_query_type_regex(query: str) -> Tuple[QueryType, float, Dict[str, float]]:
    """Classify user query using regex pattern matching.
    
    This is the original regex-based classification method used as a fallback.
    
    Args:
        query: User's message/query
        
    Returns:
        Tuple of (classification, confidence_score, all_scores)
    """
    # Direct Gmail search command
    if SEARCH_GMAIL_PATTERN.search(query):
        return "email_search", 0.95, {"email_search": 0.95}

    # Explicit request for today's email
    if TODAYS_EMAIL_PATTERN.search(query):
        return "email_search", 0.9, {"email_search": 0.9}

    # First check if the query matches any of our compiled direct lookup patterns
    if (
        TELL_ME_ABOUT_PATTERN.match(query)
        or WHO_IS_PATTERN.match(query)
        or WHAT_IS_PATTERN.match(query)
        or INFO_ON_PATTERN.match(query)
    ):
        return "notebook_lookup", 0.8, {"notebook_lookup": 0.8}
        
    # Define patterns for each category
    patterns = {
        "catch_up": [
            "what have i missed", 
            "catch me up", 
            "what's pending", 
            "todo", 
            "pending tasks", 
            "what needs action",
            "what's waiting",
            "what should i work on",
            "what's important",
            "action items",
            "needs response",
            "needs attention"
        ],
        "email_search": [
            "email", "gmail", "inbox", "find", "search", 
            "from:", "subject:", "to:", "show me", "look for",
            "messages", "sent", "received", "attachment", "label",
            "mail from", "message about", "emails about",
            "containing", "with the subject", "that mentions",
            "got any emails", "did i receive", "new mail", "in my inbox", 
            "emails today", "todays email", "today's email", "emails yesterday", "new messages", "check inbox",
            "unread emails", "my recent emails", "anything new in", "check my inbox", "check my emails", "show my inbox"
        ],
        "triage": [
            "urgent", "need to reply", "follow up", "action", 
            "priority", "important", "respond", "deadline",
            "waiting on me", "needs attention", "overdue",
            "critical", "time sensitive", "asap",
            "delegate", "virtual assistant", "hand off"
        ],
        "clarify": [
            "hi", "hello", "hey", "help", "how are you", 
            "can you", "would you", "I need", "explain",
            "what is", "how do", "could you"
        ],
        "general_chat": [
            "tell me about", "who is", "what do you know about", "explain",
            "describe", "give me a summary", "background on", "overview of",
            "research", "information on", "details about", "tell me more",
            "summarize", "brief me on", "learn about", "do research",
            "research about", "find information", "tell me what you know"
        ],
        "notebook_lookup": [
            "notebook",
            "notes on",
            "what do we know about",
            "what's in my notes",
            "my notes",
            "show notes",
            "saved notes",
            "memory about",
            "lookup",
            "find notes",
            "retrieve notes",
            "search notes",
            "tell me about",
            "who is",
            "what is",
            "what are",
            "information on",
            "details on"
        ]
    }
    
    # Get match scores for each category
    scores = calculate_pattern_match_scores(query, patterns)
    
    # Handle edge cases - very short queries default to clarify
    word_count = len(query.split())
    if word_count <= 2:
        scores["clarify"] = max(scores["clarify"], 0.8)  # Boost clarify score for very short queries
    
    # Check for explicit chat commands
    if query.lower().startswith("chat:"):
        classification = "chat"
        confidence = 1.0
        logging.info(f"[REGEX] Query explicitly marked as chat: {query[:50]}...")
        return classification, confidence, scores
    
    # Find top scoring category
    top_category = max(scores.items(), key=lambda x: x[1]) if scores else ("ambiguous", 0.0)
    category, confidence = top_category

    # Boost or override to email_search for low scoring matches
    if scores.get("email_search", 0) >= 0.03:
        if category != "email_search":
            logging.info("[REGEX] Overriding to email_search...")
        category = "email_search"
        confidence = max(confidence, THRESHOLDS['LOOKUP_LENIENT'])
    
    # If general_chat has even a modest score, prioritize it
    if scores.get("general_chat", 0) > 0.1:
        classification = "chat"
        confidence = max(confidence, scores.get("general_chat", 0))
        logging.info(f"[REGEX] Query classified as general chat: {query[:50]}...")
        return classification, confidence, scores
    
    # If confidence is too low, classify as ambiguous
    if confidence < 0.3:  # Confidence threshold
        classification = "ambiguous"
        # Log the ambiguous classification to a separate file for future improvement
        log_uncertain_classification(query, scores)
    elif category in ["triage", "vector_fallback"]:
        # Merge triage + vector_fallback into mixed_semantic
        classification = "mixed_semantic"
    elif category == "general_chat":
        # Direct chat queries to the general chat handler
        classification = "chat"
    elif category in ["email_search", "catch_up", "clarify"]:
        classification = category
    else:
        # Fall back to vector search
        classification = "vector_fallback"
        
    logging.info(f"[REGEX] Query classified as {classification} with confidence {confidence:.2f}: {query[:50]}...")
    return classification, confidence, scores


def classify_query_type(query: str, classifier: Optional[MLQueryClassifier] = None) -> Tuple[QueryType, float, Dict[str, float]]:
    """Classify user query to determine appropriate handling strategy with confidence score.
    
    Uses ML-based classification with fallback to regex pattern matching.
    
    Args:
        query: User's message/query
        classifier: An optional instance of MLQueryClassifier.
        
    Returns:
        Tuple of (classification, confidence_score, all_scores)
    """
    use_ml_result = False
    ml_scores: Dict[str, float] = {}
    prediction_from_ml: Optional[QueryType] = None # Ensure QueryType is compatible with string from ML
    confidence_from_ml = 0.0

    # Attempt ML classification if a classifier instance is provided and the class was imported
    if classifier is not None and _MLQueryClassifier_CLASS_AVAILABLE:
        try:
            # Use ML model for prediction via the passed classifier instance
            raw_ml_prediction, confidence_from_ml, ml_scores = classifier.predict(query)
            logging.info(f"ML classification for '{query[:50]}...': {raw_ml_prediction} (Confidence: {confidence_from_ml:.2f})")

            # Map 'general_chat' from ML model to 'chat' for consistency if needed by UI/handlers
            # Ensure raw_ml_prediction is a valid QueryType or can be mapped to one.
            if raw_ml_prediction == "general_chat":
                prediction_from_ml = "chat"
                logging.debug(f"Mapped ML 'general_chat' to '{prediction_from_ml}'")
            elif raw_ml_prediction in get_args(QueryType): # Validate if raw_ml_prediction is a valid QueryType
                prediction_from_ml = cast(QueryType, raw_ml_prediction)
            else:
                # Handle cases where raw_ml_prediction is not a recognized QueryType
                logging.warning(f"ML predicted an unknown label '{raw_ml_prediction}'. Treating as ambiguous.")
                prediction_from_ml = "ambiguous"
                # Optionally, adjust confidence_from_ml or ml_scores here

            # Check if ML confidence is high enough to use its result
            if confidence_from_ml >= THRESHOLDS['GENERAL'] and prediction_from_ml != "ambiguous":
                use_ml_result = True
            else:
                logging.info(f"ML confidence {confidence_from_ml:.2f} (for {prediction_from_ml}) below threshold {THRESHOLDS['GENERAL']} or ambiguous. Considering regex fallback / mixed semantic.")
                # ML result not used directly, but scores are kept for potential mixed_semantic handling later

        except ClassifierError as e:
            logging.warning(f"ML classifier prediction error: {e}. Falling back to regex.")
        except Exception as e:  # Catch-all for other unexpected errors from ML model
            logging.error(f"Unexpected error during ML classification: {e}. Falling back to regex.")

    # If ML classification was successful and meets criteria, return its result
    if use_ml_result and prediction_from_ml is not None:
        return prediction_from_ml, confidence_from_ml, ml_scores
    
    # Fallback to regex classification if ML is not used (not available, error, or low confidence)
    logging.debug(f"Using regex classification for '{query[:50]}...' (Classifier provided: {classifier is not None}, ML Class Available: {_MLQueryClassifier_CLASS_AVAILABLE}, Use ML result: {use_ml_result})")
    return classify_query_type_regex(query)


def log_uncertain_classification(query: str, scores: Dict[str, float]) -> None:
    """Log uncertain query classifications to a separate file for analysis."""
    log_dir = os.path.dirname(os.path.abspath(__file__)) + "/logs"
    os.makedirs(log_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    scores_str = ", ".join([f"{k}: {v:.2f}" for k, v in scores.items()])
    
    logger.debug(f"Logging uncertain classification for query: {query[:50]}...")
    
    with open(f"{log_dir}/uncertain_classifications.log", "a") as f:
        f.write(f"{timestamp} | Query: {query} | Scores: {scores_str}\n")


def get_classification_feedback(classification: str, confidence: float) -> str:
    """Generate a user-friendly feedback message based on classification confidence.
    
    Uses real confidence scores from the ML classifier to provide appropriate feedback.
    
    Args:
        classification: The query classification type
        confidence: The confidence score for the classification
        
    Returns:
        A formatted feedback message (empty string if confidence is high)
    """
    # Show uncertainty message for ambiguous or low confidence classifications
    # Chat queries don't need uncertainty messaging even with low confidence
    if classification in ["chat", "general_chat"]:
        return ""
        
    if classification == "ambiguous" or confidence < 0.35:
        return (
            "⚠️ I'm not totally sure what you meant, but I'll try to piece something together. "
            "You can always rephrase or correct me if needed!"
        )
    return ""

def postprocess_claude_response(response: str) -> str:
    """Clean up Claude's responses to be more concise and user-friendly.
    
    Args:
        response: Raw response from Claude
        
    Returns:
        Processed response with improved formatting and brevity
    """
    # Replace warning message with a friendlier, action-oriented alternative
    if response.startswith("⚠️"):
        response = ("I'm not sure I understood. "
                   "Could you rephrase, or should I search your inbox?")
    
    # Remove common AI self-references
    cleaned = response
    phrases_to_remove = [
        "As an AI", 
        "As your email assistant", 
        "I'm an AI", 
        "I don't have the ability to",
        "I'd be happy to",
        "I hope this helps",
        "Let me know if you need anything else"
    ]
    
    for phrase in phrases_to_remove:
        if phrase in cleaned:
            # Remove the phrase and everything until the end of that sentence
            start_idx = cleaned.find(phrase)
            if start_idx != -1:
                end_idx = cleaned.find(".", start_idx)
                if end_idx != -1:
                    # Remove the sentence containing the phrase
                    cleaned = cleaned[:start_idx] + cleaned[end_idx+1:].lstrip()
    
    # Remove redundant acknowledgments at the start
    acknowledgments = [
        "Sure!", 
        "Of course!", 
        "I'll help you with that.", 
        "Certainly!",
        "Absolutely!",
        "Here's"
    ]
    
    for ack in acknowledgments:
        if cleaned.startswith(ack):
            cleaned = cleaned[len(ack):].lstrip()
            
    # Truncate if response is too long
    if len(cleaned) > 1000:
        # Find a good break point (end of a paragraph)
        break_point = cleaned.rfind("\n\n", 0, 800)
        if break_point == -1:
            break_point = cleaned.rfind(".", 0, 800)
            if break_point == -1:
                break_point = 800
        
        cleaned = cleaned[:break_point + 1] + "\n\n...(more details available if needed)"
    
    return cleaned.strip()
