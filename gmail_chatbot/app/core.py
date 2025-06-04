#!/usr/bin/env python3

# -*- coding: utf-8 -*-

import atexit
import faulthandler
import logging
import os
import re
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    MutableMapping,
    Optional,
    Tuple,
)

os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"

if not os.environ.get("PYTEST_RUNNING"):
    faulthandler.enable()

try:
    import streamlit as st
except Exception:
    st = None

from gmail_chatbot.query_classifier import (
    classify_query_type,
    get_classification_feedback,
    postprocess_claude_response,
)
from gmail_chatbot.handlers import handle_triage_query
from .handlers import handle_email_search_query

# Pattern to detect Gmail search syntax in Claude chat responses
EMAIL_SEARCH_HINT_RE = re.compile(
    r"(from:|to:|subject:|after:|before:|label:|is:|has:|in:)", re.IGNORECASE
)

# Configure stdout/stderr for UTF-8 to properly handle emojis in console output
# Store original stdout/stderr to avoid issues during shutdown
original_stdout = sys.stdout
original_stderr = sys.stderr


# Register atexit handler to restore original streams
def restore_streams():
    """Restore original stdout/stderr streams."""
    try:
        # Use system streams directly when available
        if hasattr(sys, "__stdout__") and hasattr(sys, "__stderr__"):
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__
        else:
            # Fall back to original streams if saved
            if "original_stdout" in globals() and not getattr(
                original_stdout, "closed", True
            ):
                sys.stdout = original_stdout
            if "original_stderr" in globals() and not getattr(
                original_stderr, "closed", True
            ):
                sys.stderr = original_stderr
    except Exception:
        pass  # Silently continue if streams can't be restored


def wait_for_threads(timeout=2):
    """Wait for non-daemon threads to finish with timeout."""
    try:
        print("[INFO] Waiting for background threads to complete...")
        for thread in threading.enumerate():
            if (
                thread is threading.current_thread()
                or thread is threading.main_thread()
            ):
                continue
            if thread.is_alive() and not thread.daemon:
                print(f"[INFO] Waiting for thread {thread.name} to finish...")
                thread.join(timeout=timeout)
    except Exception as e:
        print(f"[THREAD ERROR] Error waiting for threads: {e}")


# Register handlers for cleanup
atexit.register(restore_streams)
atexit.register(wait_for_threads)

# Now import modules that depend on environment variables
from collections.abc import MutableMapping
from gmail_chatbot.email_config import (
    DEFAULT_SYSTEM_MESSAGE,
    CLAUDE_API_KEY_ENV,
    load_env,
)
from gmail_chatbot.email_claude_api import ClaudeAPIClient
from gmail_chatbot.email_gmail_api import GmailAPIClient
from gmail_chatbot.email_memory_vector import EmailVectorMemoryStore
from gmail_chatbot.gui.core import EmailChatbotGUI
from gmail_chatbot.enhanced_memory import EnhancedMemoryStore
from gmail_chatbot.query_classifier import THRESHOLDS

# Import ML classifier components
from gmail_chatbot.ml_classifier.ml_query_classifier import (
    MLQueryClassifier,
    ClassifierError,
)

# Import preference detector
from gmail_chatbot.preference_detector import PreferenceDetector

# Import memory writers for professional context
from gmail_chatbot.task_chain_parser import parse_task_chain

# Set up the logs directory path
# Store logs under the project root instead of outside the repository
LOGS_DIR = Path(__file__).resolve().parents[2] / "logs" / "gmail_chatbot"
os.makedirs(LOGS_DIR, exist_ok=True)

# Provide a placeholder for tests that patch this attribute
vector_memory = None

# Import our safe logger module for proper logging configuration and shutdown
from gmail_chatbot.safe_logger import configure_safe_logging, shutdown_logging
from gmail_chatbot.memory_handler import (
    MemoryActionsHandler,
)  # Changed from relative import

# Create a unique log file name with timestamp to prevent collisions
LOG_FILE = LOGS_DIR / f"main_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Configure safe logging with our properly isolated handlers
configure_safe_logging(LOG_FILE.resolve())


class GmailChatbotApp:
    """
    The primary application class for the Gmail Chatbot.

    This class serves as the central orchestrator for processing user queries.
    It integrates various components including:
    - QueryClassifier: To understand user intent.
    - ClaudeAPIClient: For advanced language model interactions.
    - GmailAPIClient: (Used via MemoryActionsHandler) for email-related actions.
    - MemoryActionsHandler: To manage all interactions with the memory store,
      including email storage, retrieval, summarization, and preference management.

    Key responsibilities include:
    - Receiving user messages and managing chat history.
    - Dispatching queries to specialized handler methods based on classification.
    - Managing multi-turn interactions (e.g., confirmations for email searches or tasks).
    - Coordinating autonomous tasks, such as background memory enrichment, with a
      configurable limit per session.

    The application state, including the autonomous task counter, is designed to be
    managed externally (e.g., via Streamlit session state) for persistence across
    interactions.
    """

    def __init__(
        self, autonomous_counter_ref: MutableMapping[str, int] | None = None
    ) -> None:
        print("DEBUG: GmailChatbotApp.__init__ - START")  # Added for debugging
        """Initialize the Gmail Chatbot application."""
        # Initialize attributes for component status - to be checked by chat_app_st.py
        self.gmail_service: Optional[Any] = (
            None  # Will hold the googleapiclient.discovery.Resource object
        )
        self.vector_search_available: bool = False
        self.vector_search_error_message: Optional[str] = None
        self.email_memory: Optional[Any] = (
            None  # Will hold the EmailVectorMemoryStore instance
        )
        self.claude_client: Optional[ClaudeAPIClient] = (
            None  # Initialize here, set later
        )
        self.initialization_diagnostics: List[str] = (
            []
        )  # Store detailed init steps/errors

        load_env()
        env_path = Path(__file__).resolve().parents[2] / ".env"

        # Context tracking for pending queries
        self.pending_email_context = None  # Store pending query context (original message + search string) for confirmation
        self.pending_notebook_context = (
            None  # Track follow-ups when notebook has no results
        )

        # Check for Anthropic API key
        if not os.environ.get(CLAUDE_API_KEY_ENV):
            logging.error(f"Missing {CLAUDE_API_KEY_ENV} environment variable")
            print(
                f"Error: {CLAUDE_API_KEY_ENV} environment variable is required."
            )
            error_message = (
                f"Error: {CLAUDE_API_KEY_ENV} environment variable is required. "
                f"Please make sure your .env file at {env_path} contains the Anthropic API key. "
                f"Expected format: {CLAUDE_API_KEY_ENV}=your_api_key"
            )
            print(error_message)
            raise ValueError(error_message)
        else:
            logging.info(
                f"Found {CLAUDE_API_KEY_ENV} in environment variables."
            )

        # Define path for the ML model relative to the project root
        MODEL_PATH = (
            Path(__file__).resolve().parents[1]
            / "ml_classifier"
            / "classifier_model.joblib"
        )

        # Initialize ML Query Classifier
        try:
            self.ml_classifier = MLQueryClassifier(model_path=MODEL_PATH)
            logging.info("ML Query Classifier initialized in GmailChatbotApp.")
        except ClassifierError as e:
            logging.error(
                f"Failed to initialize MLQueryClassifier in GmailChatbotApp: {e}. ML-based classification will be unavailable."
            )
            self.ml_classifier = None  # Allow app to run with regex fallback
        except FileNotFoundError:
            logging.error(
                f"ML Model file not found at {MODEL_PATH}. ML-based classification will be unavailable."
            )
            self.ml_classifier = None  # Allow app to run with regex fallback

        # Initialize components
        self.system_message = DEFAULT_SYSTEM_MESSAGE
        try:
            self.claude_client = ClaudeAPIClient()
            self.initialization_diagnostics.append(
                "✓ Claude API client initialized."
            )
        except Exception as e:
            self.claude_client = None
            self.initialization_diagnostics.append(
                f"✗ Failed to initialize Claude API client: {str(e)}"
            )
            logging.error(
                f"Failed to initialize Claude API client: {e}", exc_info=True
            )

        print(
            "DEBUG: GmailChatbotApp.__init__ - BEFORE GmailAPIClient initialization",
            file=sys.stderr,
            flush=True,
        )
        try:
            self.gmail_client = GmailAPIClient(
                self.claude_client, self.system_message
            )
            if (
                self.gmail_client
                and hasattr(self.gmail_client, "service")
                and self.gmail_client.service
            ):
                self.gmail_service = self.gmail_client.service
                self.initialization_diagnostics.append(
                    "✓ Gmail API client (and service) initialized."
                )
            else:
                self.gmail_service = (
                    None  # Explicitly set to None if service is not available
                )
                self.initialization_diagnostics.append(
                    "✗ Gmail API client initialized, but service component is missing or None."
                )
                logging.warning(
                    "GmailAPIClient initialized, but its 'service' attribute is None or missing."
                )
        except Exception as e:
            self.gmail_client = None
            self.gmail_service = None
            error_str = str(e)
            if "SSL Error" in error_str or "ssl.SSLError" in error_str:
                diag_msg = f"✗ Failed to initialize Gmail API client due to an SSL-related error: {error_str}. Possible causes: outdated Python/OpenSSL, proxy/firewall, wrong endpoint, or system clock skew."
            else:
                diag_msg = (
                    f"✗ Failed to initialize Gmail API client: {error_str}"
                )
            self.initialization_diagnostics.append(diag_msg)
            logging.error(
                f"Failed to initialize Gmail API client: {e}", exc_info=True
            )
        print(
            f"DEBUG: GmailChatbotApp.__init__ - AFTER GmailAPIClient initialization. gmail_service: {self.gmail_service}",
            file=sys.stderr,
            flush=True,
        )

        print(
            "DEBUG: GmailChatbotApp.__init__ - BEFORE vector_memory (EmailVectorStore) initialization",
            file=sys.stderr,
            flush=True,
        )
        # Initialize vector-based memory store
        try:
            self.memory_store = (
                EmailVectorMemoryStore()
            )  # This needs to set its own error message and availability
            self.email_memory = self.memory_store  # Assign the instance
            self.vector_search_available = getattr(
                self.memory_store, "vector_search_available", False
            )
            self.vector_search_error_message = getattr(
                self.memory_store, "initialization_error_message", None
            )
            if self.vector_search_available:
                self.initialization_diagnostics.append(
                    "✓ Vector-based email memory store (EmailVectorMemoryStore) initialized."
                )
                logging.info(
                    "Vector-based email memory store initialized and search is available."
                )
            else:
                err_msg = (
                    self.vector_search_error_message
                    if self.vector_search_error_message
                    else "Vector search reported as unavailable by EmailVectorMemoryStore."
                )
                self.initialization_diagnostics.append(
                    f"✗ EmailVectorMemoryStore initialized, but vector search is NOT available: {err_msg}"
                )
                logging.warning(
                    f"EmailVectorMemoryStore initialized, but vector search is NOT available: {err_msg}"
                )
        except Exception as e:
            self.memory_store = None
            self.email_memory = None
            self.vector_search_available = False
            self.vector_search_error_message = (
                f"Failed to initialize EmailVectorMemoryStore: {str(e)}"
            )
            self.initialization_diagnostics.append(
                f"✗ CRITICAL: Failed to initialize EmailVectorMemoryStore: {str(e)}"
            )
            logging.error(
                f"Failed to initialize EmailVectorMemoryStore: {e}",
                exc_info=True,
            )

        # Ensure logging reflects the final state from memory_store attributes if it was created
        if self.memory_store:
            logging.info(
                f"Vector search available (post-init check): {self.vector_search_available}, Error: {self.vector_search_error_message}"
            )
        print(
            f"DEBUG: GmailChatbotApp.__init__ - AFTER vector_memory (EmailVectorStore) attempt. vector_search_available: {self.vector_search_available}, error: {self.vector_search_error_message}",
            file=sys.stderr,
            flush=True,
        )

        # Initialize MemoryActionsHandler
        # Initialize EnhancedMemoryStore first as PreferenceDetector depends on it
        print(
            "DEBUG: GmailChatbotApp.__init__ - BEFORE EnhancedMemoryStore initialization",
            file=sys.stderr,
            flush=True,
        )
        self.enhanced_memory_store = EnhancedMemoryStore()
        print(
            "DEBUG: GmailChatbotApp.__init__ - AFTER EnhancedMemoryStore initialization",
            file=sys.stderr,
            flush=True,
        )
        logging.info("Enhanced memory store initialized")

        # Initialize PreferenceDetector
        print(
            "DEBUG: GmailChatbotApp.__init__ - BEFORE PreferenceDetector initialization",
            file=sys.stderr,
            flush=True,
        )
        self.preference_detector = PreferenceDetector(
            memory_store=self.enhanced_memory_store
        )
        print(
            "DEBUG: GmailChatbotApp.__init__ - AFTER PreferenceDetector initialization",
            file=sys.stderr,
            flush=True,
        )
        logging.info("Preference detector initialized")

        # Initialize MemoryActionsHandler
        print(
            "DEBUG: GmailChatbotApp.__init__ - BEFORE MemoryActionsHandler initialization",
            file=sys.stderr,
            flush=True,
        )
        self.memory_actions_handler = MemoryActionsHandler(
            memory_store=self.memory_store,
            gmail_client=self.gmail_client,
            claude_client=self.claude_client,
            system_message=self.system_message,
            preference_detector=self.preference_detector,  # Added this line
        )
        print(
            f"DEBUG: GmailChatbotApp.__init__ - AFTER MemoryActionsHandler initialization. memory_actions_handler: {self.memory_actions_handler}",
            file=sys.stderr,
            flush=True,
        )

        # Add the three main clients to memory if not already present using MemoryActionsHandler
        default_clients = [
            "Further Learner",
            "Excel High School",
            "Hoorah Digital",
        ]
        current_clients_in_memory = (
            self.memory_actions_handler.get_handler_client_names()
        )
        for client_name in default_clients:
            if client_name not in current_clients_in_memory:
                self.memory_actions_handler.add_handler_client_info(
                    client_name, {"status": "active"}
                )
                logging.info(
                    f"Added client {client_name} to memory store via MemoryActionsHandler"
                )

        # Chat history for context
        self.chat_history: List[Dict[str, str]] = []

        # Track if the enrichment thread has been started for this session
        self.autonomous_thread_started = False
        if st is not None and hasattr(st, "session_state"):
            st.session_state.setdefault("autonomous_thread_started", False)
            self.autonomous_thread_started = (
                st.session_state.autonomous_thread_started
            )

        # Counter for tracking autonomous task steps, referenced from Streamlit session state
        self.counter = (
            autonomous_counter_ref
            if autonomous_counter_ref is not None
            else {"autonomous_task_counter": 0}
        )
        if autonomous_counter_ref is None:
            logging.warning(
                f"[{self.__class__.__name__}] Initialized with a local autonomous_task_counter. For persistence, provide a MutableMapping reference."
            )
        else:
            # Ensure the key exists if the reference is provided (self.counter is autonomous_counter_ref here)
            if "autonomous_task_counter" not in self.counter:
                self.counter["autonomous_task_counter"] = 0
                logging.info(
                    f"[{self.__class__.__name__}] Initialized 'autonomous_task_counter' in shared reference (id: {id(self.counter)}). Current value: {self.counter['autonomous_task_counter']}"
                )
            else:
                logging.info(
                    f"[{self.__class__.__name__}] Using shared autonomous_task_counter (id: {id(self.counter)}), current value: {self.counter['autonomous_task_counter']}"
                )

        # Start autonomous memory enrichment in a background thread only once
        if not self.autonomous_thread_started:
            enrichment_request_id = str(uuid.uuid4())
            logging.info(
                f"[{enrichment_request_id}] Initiating background autonomous memory enrichment task in __init__."
            )
            enrichment_thread = threading.Thread(
                target=self.memory_actions_handler.perform_autonomous_memory_enrichment,
                args=(enrichment_request_id,),
                daemon=True,
                name="AutonomousMemoryEnrichmentThread",
            )
            enrichment_thread.start()
            self.autonomous_thread_started = True
            if st is not None and hasattr(st, "session_state"):
                st.session_state.autonomous_thread_started = True
        else:
            logging.info(
                "Autonomous memory enrichment thread already started; skipping"
            )

        logging.info("Gmail Chatbot application initialized")
        print("DEBUG: GmailChatbotApp.__init__ - END")  # Added for debugging

    def test_gmail_api_connection(self) -> Tuple[bool, str]:
        """Tests the connection to the Gmail API by fetching the user's profile.
        Returns a tuple: (bool: success, str: message).
        """
        logging.info("Attempting to test Gmail API connection...")
        print("DEBUG: GmailChatbotApp.test_gmail_api_connection - START")
        # Check if the gmail_client itself was initialized, not just the service attribute
        if not self.gmail_client:
            msg = "✗ Gmail API client (GmailAPIClient instance) not initialized. Cannot test connection."
            logging.error(msg)
            print(f"DEBUG: GmailChatbotApp.test_gmail_api_connection - {msg}")
            # self.initialization_diagnostics.append(msg) # This might be redundant if init already logged it
            return False, msg

        # Call the test_connection method of the GmailAPIClient instance
        result_dict = self.gmail_client.test_connection()

        success = result_dict.get("success", False)
        message = result_dict.get(
            "message", "Unknown error during connection test."
        )
        error_type = result_dict.get("error_type")

        if success:
            msg = f"✓ Gmail API connection test successful: {message}"
            logging.info(msg)
            print(
                f"DEBUG: GmailChatbotApp.test_gmail_api_connection - SUCCESS: {message}"
            )
            self.initialization_diagnostics.append(msg)
            return True, msg
        else:
            # Construct a detailed message based on error type
            if error_type == "ssl_error":
                # The message from GmailAPIClient.test_connection for ssl_error is already detailed.
                msg = f"✗ Gmail API SSL Error: {message}"
            elif error_type == "auth_refresh_error":
                msg = f"✗ Gmail API Authentication Error (Token Refresh Failed): {message}. Please try re-authenticating."
            elif error_type == "auth_error":
                msg = f"✗ Gmail API Authentication Error: {message}. Check credentials or re-authenticate."
            elif error_type == "api_error":
                status_code = result_dict.get("status_code")
                code_info = (
                    f" (Status Code: {status_code})" if status_code else ""
                )
                msg = f"✗ Gmail API Error{code_info}: {message}"
            else:  # unknown_error or other
                msg = f"✗ Gmail API connection test FAILED: {message}"

            logging.error(
                f"Gmail API connection test FAILED ({error_type if error_type else 'Unknown'}): {message}",
                exc_info=(error_type == "unknown_error"),
            )
            print(
                f"DEBUG: GmailChatbotApp.test_gmail_api_connection - FAILED ({error_type}): {message}"
            )
            self.initialization_diagnostics.append(msg)
            return False, msg

    def get_vector_search_error_message(self) -> Optional[str]:
        """Returns the stored error message from vector search initialization, if any."""
        return self.vector_search_error_message

    def get_last_assistant_reply(self) -> Optional[str]:
        """Return the most recent assistant message from ``chat_history``."""
        for message in reversed(self.chat_history):
            if message.get("role") == "assistant":
                return message.get("content")
        return None

    def has_recent_assistant_phrase(
        self, phrase: str, lookback: int = 3
    ) -> bool:
        """Check if the last few assistant replies contain ``phrase``.

        Parameters
        ----------
        phrase:
            Phrase to search for (case-insensitive).
        lookback:
            Number of assistant messages to inspect from the end of
            ``chat_history``.

        Returns
        -------
        bool
            ``True`` if ``phrase`` was found in the recent assistant replies.
        """
        remaining = lookback
        for message in reversed(self.chat_history):
            if message.get("role") != "assistant":
                continue
            content = message.get("content", "").lower()
            if phrase.lower() in content:
                return True
            remaining -= 1
            if remaining <= 0:
                break
        return False

    def get_notebook_overview(self, request_id: str) -> str:
        """Return a concise overview of the notebook contents."""
        return self.memory_actions_handler.get_notebook_overview(request_id)

    def _is_simple_inbox_query(self, message_lower: str) -> bool:
        """Checks if a query is a simple request for inbox contents, suitable for a menu."""
        generic_inbox_phrases = [
            "check my inbox",
            "check inbox",
            "my inbox",
            "show my inbox",
            "show my emails",
            "unread emails",
            "recent unread",
            "any new mail",
            "what's new",
            "new emails",
            "check my mail",
            "see my emails",
            "view my inbox",
        ]
        # Query must contain at least one generic phrase
        if not any(
            phrase in message_lower for phrase in generic_inbox_phrases
        ):
            return False

        # Check for complexity keywords that suggest a specific search beyond a simple menu
        complexity_keywords = [
            "from:",
            "to:",
            "subject:",
            "after:",
            "before:",
            "label:",
            "has:attachment",
            "keyword:",
            "regarding",
            "about",
            "concerning",
        ]
        if any(keyword in message_lower for keyword in complexity_keywords):
            # Allow "after:today" or "after:yesterday" if part of a generic phrase like "unread emails after today"
            if not (
                (
                    "after:today" in message_lower
                    or "after:yesterday" in message_lower
                )
                and "unread" in message_lower
            ):
                return False

        # Check for too many specific terms (simple heuristic)
        # Remove generic phrases to count remaining specific terms
        temp_message = message_lower
        for phrase in generic_inbox_phrases:
            temp_message = temp_message.replace(phrase, "")

        # Count remaining words that are not common (stopwords could be used here for more accuracy)
        specific_words = [
            word
            for word in temp_message.split()
            if len(word) > 2
            and word not in ["my", "me", "i", "is", "are", "a", "the"]
        ]
        if (
            len(specific_words) > 1
        ):  # If more than 1 potentially specific term remains, it's likely not for a generic menu
            return False
        return True

    def _handle_email_menu_choice(self, choice: str, request_id: str) -> str:
        """Handles numeric choices from a previously presented email options menu."""
        logging.info(f"[{request_id}] Handling email menu choice: {choice}")

        if (
            not self.pending_email_context
            or self.pending_email_context.get("type") != "email_menu"
        ):
            logging.warning(
                f"[{request_id}] _handle_email_menu_choice called without valid pending_email_context."
            )
            self.pending_email_context = None
            return "It seems there was no active menu. How can I help you?"

        options_map = self.pending_email_context.get("options", {})
        action_details = options_map.get(choice)

        response = f"Okay, you selected option {choice}."

        if action_details:
            action_type = action_details.get("type")
            query_text = action_details.get("query", "the selected option")
            # original_user_message = self.pending_email_context.get("original_message", "your previous request") # Available if needed

            logging.info(
                f"[{request_id}] Menu choice '{choice}' maps to action: {action_type}, query: '{query_text}'"
            )

            if action_type == "search_emails":
                original_user_message = self.pending_email_context.get(
                    "original_message", query_text
                )  # Fallback to query_text if original_message somehow missing
                logging.info(
                    f"[{request_id}] Executing email search from menu. Query: '{query_text}', Original user msg: '{original_user_message[:50]}'"
                )

                gmail_search_string = query_text
                logging.critical(
                    f"[{request_id}] user-initiated search_emails using: {gmail_search_string}"
                )
                emails, search_response_text = self.gmail_client.search_emails(
                    query=query_text,  # Use the specific query from the menu
                    original_user_query=original_user_message,
                    system_message=self.system_message,
                    request_id=request_id,
                )
                if (
                    search_response_text
                    and "error" in search_response_text.lower()
                    and st
                ):
                    st.session_state.last_gmail_error = search_response_text
                response = search_response_text

                if emails:
                    logging.info(
                        f"[{request_id}] Found {len(emails)} emails from menu-driven search for '{query_text}'."
                    )
                    self.memory_actions_handler.store_emails_in_memory(
                        emails=emails, query=query_text, request_id=request_id
                    )  # Store with the specific Gmail query
                    if (
                        not response
                    ):  # If gmail_client didn't provide a summary response
                        response = f"I found {len(emails)} email(s) matching your selection: '{query_text}'. They have been processed."
                else:
                    logging.info(
                        f"[{request_id}] No emails found from menu-driven search for '{query_text}'."
                    )
                    if (
                        not response
                    ):  # If gmail_client didn't provide a no-results response
                        response = f"I couldn't find any emails matching your selection for '{query_text}'."

            # Add more elif action_type == "..." blocks here for other menu actions
            else:
                logging.warning(
                    f"[{request_id}] Unknown or unhandled action_type '{action_type}' for choice '{choice}'."
                )
                response = f"I've noted your selection of option {choice} for '{query_text}', but the specific action isn't fully set up yet."

            self.pending_email_context = (
                None  # Clear context after processing a valid choice
            )
        else:
            logging.warning(
                f"[{request_id}] Invalid menu choice: {choice}. Valid options were: {list(options_map.keys())}"
            )
            response = "That wasn't a valid option from the menu. Please try again with one of the listed numbers, or ask something else."
            # Do not clear pending_email_context here, so user can try again with a valid number.

        return response

    def _handle_catch_up_query(self, request_id: str) -> str:
        """Handles queries classified as 'catch_up'."""
        logging.info(
            f"[{request_id}] Delegating 'catch_up' query to MemoryActionsHandler.get_action_items."
        )
        # Assuming self.memory_actions_handler.get_action_items() returns a string response.
        # The main process_message loop will append this to chat_history.
        return self.memory_actions_handler.get_action_items()

    def _handle_notebook_lookup_query(
        self, message: str, request_id: str
    ) -> str:
        """Handles queries classified as 'notebook_lookup'."""
        logging.info(f"[{request_id}] Handling 'notebook_lookup' query.")
        # Use memory store to search for related notes and preferences
        search_results = self.memory_actions_handler.query_memory(
            message, request_id=request_id
        )
        response = ""  # Initialize response

        if search_results:
            # Format the results in a notebook-style response
            response_parts = ["📓 **From my notebook:**\n"]

            for idx, result in enumerate(search_results, 1):
                search_type = result.get("search_type", "unknown")
                subject = result.get("subject", "Untitled note")
                summary = result.get("summary", "No details available")
                date = result.get("date", "Unknown date")
                score = result.get("relevance_score", 0)

                response_parts.append(f"**{idx}. {subject}**")
                response_parts.append(f"- {summary}")
                response_parts.append(
                    f"- *Date: {date} · Relevance: {score}/10 · Found via {search_type} search*\n"
                )

            # Add a note about search method used
            has_vector = any(
                r.get("search_type") == "vector" for r in search_results
            )
            has_keyword = any(
                r.get("search_type") == "keyword" for r in search_results
            )

            if has_vector and has_keyword:
                response_parts.append(
                    "*Note: Results include both vector semantic matches and keyword matches.*"
                )
            elif has_vector:
                response_parts.append(
                    "*Note: Results found using vector semantic search.*"
                )
            elif has_keyword:
                response_parts.append(
                    "*Note: Results found using keyword search.*"
                )

            response = "\n".join(response_parts)
        else:
            # Locally import patterns and templates to keep scope tight, and define Enum
            # Note: 'Enum' and 're' are already globally imported but included here for completeness of this block
            from enum import Enum
            import re
            from ..query_classifier import (
                TELL_ME_ABOUT_PATTERN,
                WHO_IS_PATTERN,
                WHAT_IS_PATTERN,
                INFO_ON_PATTERN,
            )

            # Ensure prompt_templates.py exists and contains NOTEBOOK_NO_RESULTS_TEMPLATES
            from ..prompt_templates import NOTEBOOK_NO_RESULTS_TEMPLATES

            class NotebookMissAction(Enum):
                SEARCH_GMAIL = "search_gmail"
                CREATE_NOTE = "create_note"
                NONE = "none"

            entity = None
            # Assuming these patterns are pre-compiled regex objects from query_classifier.py
            tell_match = TELL_ME_ABOUT_PATTERN.search(message)
            who_match = WHO_IS_PATTERN.search(message)
            what_match = WHAT_IS_PATTERN.search(message)
            info_match = INFO_ON_PATTERN.search(message)

            if tell_match:
                entity = tell_match.group(1).strip()
            elif who_match:
                entity = who_match.group(1).strip()
            elif what_match:  # Typically r"(what is|what's)\s+(.+?)\?*$"
                entity = what_match.group(2).strip()
            elif (
                info_match
            ):  # Typically r"(info on|information on)\s+(.+?)\?*$"
                entity = info_match.group(2).strip()

            if entity:
                entity = re.sub(r'[\\"\']', "", entity).strip()

            follow_up = {
                "action": NotebookMissAction.SEARCH_GMAIL,
                "entity": entity,
                "original_query": message,
            }

            if entity:
                response = NOTEBOOK_NO_RESULTS_TEMPLATES["with_entity"].format(
                    entity=entity
                )
            else:
                response = NOTEBOOK_NO_RESULTS_TEMPLATES["generic"]

            # Store context for potential follow-up
            self.pending_notebook_context = follow_up

            search_query = (
                f"from:{entity} OR to:{entity} OR subject:{entity}"
                if entity
                else message
            )
            # Reuse confirmation context but proceed with the search immediately

            self.pending_email_context = {
                "gmail_query": search_query,
                "original_message": message,
                "type": "gmail_query_confirmation",
            }

            logging.info(
                f"[{request_id}] Notebook miss for query: '{message[:50]}...'. "
                f"Auto searching Gmail with: '{search_query}'"
            )

            emails, search_results_text = self.gmail_client.search_emails(
                query=search_query,
                original_user_query=message,
                system_message=self.system_message,
                request_id=request_id,
            )
            if (
                search_results_text
                and "error" in search_results_text.lower()
                and st
            ):
                st.session_state.last_gmail_error = search_results_text

            final_parts = [response]
            if emails:
                logging.info(
                    f"[{request_id}] Found {len(emails)} emails from auto search."
                )
                self.memory_actions_handler.store_emails_in_memory(
                    emails=emails,
                    query=message,
                    request_id=request_id,
                )
                email_ids = [e.get("id") for e in emails if e.get("id")]
                self.memory_actions_handler.record_interaction_in_memory(
                    query=message,
                    response=search_results_text
                    or f"Found {len(emails)} emails.",
                    request_id=request_id,
                    email_ids=email_ids,
                    client=None,
                )
                if search_results_text:
                    final_parts.append(search_results_text)
                else:
                    final_parts.append(
                        f"I found {len(emails)} email(s) matching `{search_query}`."
                    )
            else:
                logging.info(
                    f"[{request_id}] No emails found for auto search query: '{search_query[:50]}'"
                )
                if search_results_text:
                    final_parts.append(search_results_text)
                else:
                    final_parts.append(
                        f"I searched Gmail for `{search_query}` but couldn't find any matching emails."
                    )

            response = "\n\n".join(filter(None, final_parts))
            self.pending_email_context = None


        # Log the notebook search (hit or miss) via MemoryActionsHandler
        self.memory_actions_handler.record_interaction_in_memory(
            query=message,
            response=response,
            request_id=request_id,
            client=None,  # Or derive client if applicable
        )
        return response

    def _handle_vector_fallback_query(
        self, message: str, query_type: str, confidence: float, request_id: str
    ) -> str:
        """Handles 'vector_fallback' or general 'ambiguous' queries using vector search, potentially with semantic reasoning."""
        logging.info(
            f"[{request_id}] Handling 'vector_fallback' or general 'ambiguous' query (type: {query_type}, confidence: {confidence:.2f}) with vector search."
        )
        response = ""  # Initialize response
        search_query = message  # Default search query

        # Import the semantic reasoning prompt locally if needed
        from ..prompt_templates import SEMANTIC_REASONING_PROMPT

        # For ambiguous queries with low confidence, first perform semantic reasoning
        if query_type == "ambiguous" and confidence < 0.4:
            logging.info(
                f"[{request_id}] Using SEMANTIC_REASONING_PROMPT to guide vector search for ambiguous query"
            )
            reasoning_prompt = f"{SEMANTIC_REASONING_PROMPT}\n\nUser query: {message}\n\nPlease analyze this query and determine appropriate keywords for semantic search."
            modified_system_message = (
                self.system_message
                + "\n\nYou have access to a vector database of emails. Use it proactively for vague queries."
            )
            vector_reasoning = self.claude_client.process_query(
                user_query=reasoning_prompt,
                system_message=modified_system_message,
                request_id=f"{request_id}_reasoning",
                model=self.claude_client.prep_model,
            )
            if vector_reasoning.startswith("VECTOR_SEARCH:"):
                extracted_terms = vector_reasoning.replace(
                    "VECTOR_SEARCH:", ""
                ).strip()
                if extracted_terms:
                    search_query = extracted_terms
                    logging.info(
                        f"[{request_id}] Claude extracted search terms: '{search_query}'"
                    )
                else:
                    logging.info(
                        f"[{request_id}] Claude did not extract specific search terms, using original query."
                    )
            else:
                logging.info(
                    f"[{request_id}] Semantic reasoning didn't return VECTOR_SEARCH format, using original query."
                )

        # Now perform the vector search with potentially enhanced query
        if self.memory_store.vector_search_available:
            limit = (
                3
                if confidence < THRESHOLDS["VECTOR_SEARCH"]["HIGH_CONFIDENCE"]
                else 8
            )
            min_score = THRESHOLDS["VECTOR_SEARCH"]["MIN_RELEVANCE"]

            vector_results = self.memory_actions_handler.query_memory(
                search_query, request_id=request_id
            )

            if vector_results:
                enhanced_system = (
                    self.system_message
                    + "\n\nIMPORTANT: Each context item has a relevance score. Pay careful attention to these scores - higher scores (closer to 10) indicate more relevant information. For items with low scores (below 5), be very cautious about using the information and clearly indicate uncertainty if needed."
                )
                for result in vector_results:
                    if "relevance_score" in result:
                        score = result["relevance_score"]
                        formatted_score = f"{score:.2f}"
                        result["display_header"] = (
                            f"### Context (Relevance: {formatted_score}/10)"
                        )

                seen_content = set()
                unique_results = []
                for result in vector_results:
                    content_hash = hash(
                        result.get("body", "") + result.get("subject", "")
                    )
                    if content_hash not in seen_content:
                        seen_content.add(content_hash)
                        unique_results.append(result)
                vector_results = unique_results  # Use deduplicated results

                raw_response = self.claude_client.evaluate_vector_match(
                    user_query=message,  # Original message for evaluation context
                    vector_results=vector_results,
                    system_message=enhanced_system,
                    request_id=request_id,  # Added request_id, removed context
                )
                response = postprocess_claude_response(raw_response)
            else:
                response = "I tried a general search based on your query but couldn't find relevant information in my current knowledge."
        else:
            response = "I'm not sure how to best handle that request, and my semantic search capability is currently unavailable."

        # Record the interaction
        self.memory_actions_handler.record_interaction_in_memory(
            original_user_query=message,
            final_response=response,
            request_id=request_id,
            query_type=query_type,  # Original query_type ('vector_fallback' or 'ambiguous')
            search_method="vector_fallback_search",
            # Not adding specific vector_results or search_query to meta for now to keep it simple
        )
        return response

    def _handle_mixed_semantic_query(
        self, message: str, request_id: str
    ) -> str:
        """Handles queries classified as 'mixed_semantic'."""
        logging.info(
            f"[{request_id}] Handling 'mixed_semantic' query with combined triage and vector search."
        )
        response = ""
        if self.memory_store.vector_search_available:
            vector_results = self.memory_actions_handler.query_memory(
                message, request_id=request_id
            )
            if vector_results:
                raw_response = self.claude_client.evaluate_vector_match(
                    user_query=message,
                    vector_results=vector_results,
                    system_message=self.system_message,
                    request_id=request_id,
                )
                response = postprocess_claude_response(raw_response)
            else:
                response = "I searched for content related to your query but couldn't find anything relevant in your emails."
        else:
            response = "I'm not sure how to best handle that request, and my semantic search capability is currently unavailable."

        self.memory_actions_handler.record_interaction_in_memory(
            query=message,
            response=response,
            request_id=request_id,
            client=None,
        )
        return response

    def _handle_general_chat_query(
        self, message: str, query_type: str, request_id: str
    ) -> str:
        """Handles queries classified as 'clarify', 'chat', or low-confidence 'ambiguous'."""
        logging.info(
            f"[{request_id}] Handling '{query_type}' query as general chat."
        )
        # Route to Claude's chat method
        # Pass self.chat_history[:-1] to exclude the current user message which Claude will get as 'message'
        response = self.claude_client.chat(
            message, self.chat_history[:-1], self.system_message
        )
        response = postprocess_claude_response(
            response
        )  # Ensure consistent post-processing

        search_text = self._maybe_search_from_response(
            response, message, request_id
        )
        if search_text:
            response = f"{response}\n\n{search_text}"

        # Record the general chat interaction via MemoryActionsHandler
        # This assumes record_interaction_in_memory can handle general chats without email_ids or client
        self.memory_actions_handler.record_interaction_in_memory(
            query=message, response=response, request_id=request_id
        )
        return response

    def _maybe_search_from_response(
        self, response: str, original_query: str, request_id: str
    ) -> Optional[str]:
        """Trigger a Gmail search if Claude's chat response contains Gmail syntax."""
        if not self.gmail_client:
            return None
        if not EMAIL_SEARCH_HINT_RE.search(response):
            return None
        gmail_query = self.gmail_client._extract_gmail_search_query(response)
        logging.info(
            f"[{request_id}] Detected Gmail query in chat response: {gmail_query}"
        )
        gmail_search_string = gmail_query
        logging.critical(
            f"[{request_id}] user-initiated search_emails using: {gmail_search_string}"
        )
        emails, search_results_text = self.gmail_client.search_emails(
            gmail_query,
            original_user_query=original_query,
            system_message=self.system_message,
            request_id=request_id,
        )
        if emails:
            self.memory_actions_handler.store_emails_in_memory(
                emails=emails, query=original_query, request_id=request_id
            )
        return search_results_text

    def handle_pending_email_menu(
        self, message_lower: str, request_id: str
    ) -> Optional[str]:
        """Handle numeric selections when an email menu is active."""
        if (
            self.pending_email_context
            and self.pending_email_context.get("type") == "email_menu"
            and message_lower.isdigit()
        ):
            choice_str = message_lower
            if choice_str in self.pending_email_context.get("options", {}):
                logging.info(
                    f"[{request_id}] Detected numeric input '{choice_str}' for active email menu."
                )
                response = self._handle_email_menu_choice(
                    choice_str, request_id
                )
                self.chat_history.append(
                    {"role": "assistant", "content": response}
                )
                return response
            logging.info(
                f"[{request_id}] Numeric input '{choice_str}' is not a valid option for the current menu."
            )
        return None

    def handle_confirmation(
        self, message: str, message_lower: str, request_id: str
    ) -> Optional[str]:
        """Handle user confirmations or cancellations for pending actions."""
        if self.pending_email_context and message_lower in {
            "no",
            "n",
            "cancel",
            "stop",
        }:
            confirmed_query_text = self.pending_email_context.get(
                "gmail_query", "the previous action"
            )
            logging.info(
                f"[{request_id}] User cancelled pending action for: {confirmed_query_text[:50]}..."
            )
            response = (
                f"Okay, I've cancelled the action regarding `{confirmed_query_text}`. "
                "The task counter has been reset. How else can I help?"
            )
            self.pending_email_context = None
            self.counter["autonomous_task_counter"] = 0
            logging.info(
                f"[{request_id}] Autonomous task counter reset to 0 due to user cancellation."
            )
            self.chat_history.append(
                {"role": "assistant", "content": response}
            )
            return response

        if len(self.chat_history) >= 2:
            last_assistant_msg = self.get_last_assistant_reply()
            if (
                last_assistant_msg
                and "TASK_CHAIN:" in last_assistant_msg
                and message_lower
                in {"yes", "y", "sure", "go ahead", "continue", "proceed"}
            ):
                logging.info(
                    f"[{request_id}] User confirmed TASK_CHAIN execution"
                )
                self.autonomous_task_counter = 0

                plan_lower = last_assistant_msg.lower()
                if "enrich" in plan_lower and "memory" in plan_lower:
                    logging.info(
                        f"[{request_id}] User confirmed TASK_CHAIN. Initiating autonomous memory enrichment."
                    )
                    self.memory_actions_handler.perform_autonomous_memory_enrichment(
                        request_id=request_id
                    )
                    response = (
                        "I've initiated a memory enrichment process based on your confirmation. "
                        "You can continue interacting."
                    )
                    self.chat_history.append(
                        {"role": "assistant", "content": response}
                    )
                    return response

                try:
                    plan = parse_task_chain(last_assistant_msg)
                except Exception as e:  # pragma: no cover - defensive
                    logging.error(
                        f"[{request_id}] Failed to parse TASK_CHAIN: {e}"
                    )
                    plan = []

                if plan and st:
                    st.session_state.agentic_plan = plan
                    st.session_state.agentic_state = {
                        "current_step_index": 0,
                        "executed_call_count": 0,
                        "accumulated_results": {},
                        "error_messages": [],
                    }
                    try:  # Delayed import to avoid circular dependency
                        from chat_app_st import run_agentic_plan  # type: ignore

                        run_agentic_plan()
                    except Exception as e:  # pragma: no cover - defensive
                        logging.error(
                            f"[{request_id}] Error running agentic plan: {e}"
                        )

                response = "Okay, I'm starting that task chain."
                self.chat_history.append(
                    {"role": "assistant", "content": response}
                )
                return response

        if self.pending_email_context:
            user_input_lower = message_lower
            pending_type = self.pending_email_context.get("type")

            affirmatives = {
                "yes",
                "y",
                "sure",
                "okay",
                "ok",
                "go ahead",
                "please do",
                "search",
                "yep",
                "yeah",
                "affirmative",
                "do it",
                "proceed",
                "sounds good",
                "correct",
            }

            if pending_type == "gmail_query_confirmation":
                gmail_search_string = self.pending_email_context.get(
                    "gmail_query", "your previous email search"
                )
                original_user_message = self.pending_email_context.get(
                    "original_message"
                )
                ambiguous = {
                    "maybe",
                    "not sure",
                    "hmm",
                    "hm",
                    "possibly",
                    "i'm not sure",
                    "i dont know",
                    "i don't know",
                }

                if user_input_lower in affirmatives:
                    logging.info(
                        f"[{request_id}] User affirmatively confirmed pending Gmail query: {gmail_search_string[:50]}..."
                    )
                    self.pending_email_context = None
                    acknowledgement = "👍 Starting the search now..."
                    logging.critical(
                        f"[{request_id}] user-initiated search_emails using: {gmail_search_string}"
                    )
                    emails, search_results_text = (
                        self.gmail_client.search_emails(
                            query=gmail_search_string,
                            original_user_query=original_user_message,
                            system_message=self.system_message,
                            request_id=request_id,
                        )
                    )
                    if (
                        search_results_text
                        and "error" in search_results_text.lower()
                        and st
                    ):
                        st.session_state.last_gmail_error = search_results_text
                    final_parts = [acknowledgement]
                    if emails:
                        logging.info(
                            f"[{request_id}] Found {len(emails)} emails from confirmed search. Storing."
                        )
                        self.memory_actions_handler.store_emails_in_memory(
                            emails=emails,
                            query=original_user_message,
                            request_id=request_id,
                        )
                        email_ids = [
                            e.get("id") for e in emails if e.get("id")
                        ]
                        self.memory_actions_handler.record_interaction_in_memory(
                            query=original_user_message,
                            response=search_results_text
                            or f"Found {len(emails)} emails.",
                            request_id=request_id,
                            email_ids=email_ids,
                            client=None,
                        )
                        if search_results_text:
                            final_parts.append(search_results_text)
                        else:
                            final_parts.append(
                                f"I found {len(emails)} email(s) matching your search for `{gmail_search_string}`. They have been processed and stored."
                            )
                    else:
                        logging.info(
                            f"[{request_id}] No emails found for confirmed query: {gmail_search_string[:50]}"
                        )
                        if search_results_text:
                            final_parts.append(search_results_text)
                        else:
                            final_parts.append(
                                f"I searched for `{gmail_search_string}` but couldn't find any matching emails."
                            )
                    response = "\n\n".join(filter(None, final_parts))
                    self.chat_history.append(
                        {"role": "assistant", "content": response}
                    )
                    return response
                if user_input_lower in ambiguous:
                    logging.info(
                        f"[{request_id}] Ambiguous response ('{user_input_lower}') to Gmail query confirmation for '{gmail_search_string}'. Re-prompting."
                    )
                    response = f"Sorry, I didn't quite catch that. Did you want me to proceed with the search for `{gmail_search_string}`? (yes/no)"
                    self.chat_history.append(
                        {"role": "assistant", "content": response}
                    )
                    return response

                logging.info(
                    f"[{request_id}] User input '{user_input_lower[:30]}' received during Gmail query confirmation for '{gmail_search_string[:50]}...' is not affirmative or specifically ambiguous. Will treat as new query."
                )
                self.pending_email_context = None

            logging.info(
                f"[{request_id}] User provided new input ('{message[:20]}...') while a '{pending_type}' confirmation was pending. Proceeding with new input."
            )
        return None

    def handle_query_classification(
        self, message: str, request_id: str
    ) -> str:
        """Classify a message and route it to specific handlers."""
        query_type, confidence, scores = classify_query_type(
            message, classifier=self.ml_classifier
        )
        uncertainty_message = get_classification_feedback(
            query_type, confidence
        )
        logging.info(
            f"[{request_id}] Classified query: type='{query_type}', confidence={confidence:.2f}, scores={scores}, uncertainty_feedback_provided='{bool(uncertainty_message)}'"
        )
        message_lower = message.lower().strip()
        response = ""
        if query_type == "catch_up":
            logging.info(f"[{request_id}] Handling 'catch_up' query.")
            response = self._handle_catch_up_query(request_id)
        elif query_type in {"clarify", "chat"} or (
            query_type == "ambiguous" and confidence < 0.25
        ):
            response = self._handle_general_chat_query(
                message, query_type, request_id
            )
        elif query_type == "triage" or (
            query_type == "ambiguous" and scores.get("triage", 0) > 0.2
        ):
            response = handle_triage_query(self, message, request_id, scores)
        elif query_type == "email_search":
            response = handle_email_search_query(
                self, message, message_lower, request_id
            )
        elif query_type == "notebook_lookup":
            response = self._handle_notebook_lookup_query(message, request_id)
        elif query_type == "mixed_semantic":
            response = self._handle_mixed_semantic_query(message, request_id)
        elif query_type == "vector_fallback" or (
            query_type == "ambiguous" and not response
        ):
            response = self._handle_vector_fallback_query(
                message, query_type, confidence, request_id
            )

        if not response:
            response = self._handle_unknown_or_fallback_query(
                message, query_type, request_id
            )
            if uncertainty_message and not self.pending_email_context:
                response = uncertainty_message + "\n\n" + response
        return response

    def process_message(
        self, message: str, request_id: str | None = None
    ) -> str:
        """Process a user message and return the assistant's response."""
        if request_id is None:
            request_id = str(uuid.uuid4())
        logging.info(
            f"[{request_id}] Processing message (first 50 chars): '{message[:50]}...'"
        )

        proactive_updates_list = (
            self.memory_actions_handler.get_pending_proactive_summaries()
        )
        proactive_response_part = ""
        if proactive_updates_list:
            proactive_response_part = "\n\n".join(proactive_updates_list)
            if proactive_response_part:
                proactive_response_part = f"🔔 **Background Updates:**\n{proactive_response_part}\n\n---\n\n"
                logging.info(
                    f"[{request_id}] Retrieved proactive updates: {proactive_response_part[:100]}..."
                )

        self.chat_history.append({"role": "user", "content": message})
        message_lower = message.lower().strip()

        menu_response = self.handle_pending_email_menu(
            message_lower, request_id
        )
        if menu_response:
            return proactive_response_part + menu_response

        confirm_response = self.handle_confirmation(
            message, message_lower, request_id
        )
        if confirm_response:
            return proactive_response_part + confirm_response

        note_cmds = [
            "create note",
            "create notes",
            "remember this",
            "note this",
        ]
        for cmd in note_cmds:
            if message_lower.startswith(cmd):
                text = message[len(cmd) :].strip()
                if not text:
                    text = self.get_last_assistant_reply() or ""
                if not text:
                    response = "I couldn't find text to save as a note."
                else:
                    if self.enhanced_memory_store.save_note_from_text(text):
                        response = (
                            "\U0001f4d3 Saved that note."  # notebook emoji
                        )
                    else:
                        response = "Couldn't save the note due to an error."
                self.chat_history.append(
                    {"role": "assistant", "content": response}
                )
                return proactive_response_part + response

        # Check for explicit preference memory instructions
        memory_triggers = [
            "remember that",
            "store this",
            "log this about me",
            "my preference is",
            "note that i",
            "remember i",
        ]
        # First, try using the automatic preference detector
        is_preference, feedback = self.preference_detector.process_message(
            message
        )

        if is_preference:
            # A preference was automatically detected and stored
            logging.info(
                f"[{request_id}] Automatically detected and stored user preference"
            )
            response = self.claude_client.chat(
                messages=self.chat_history
            ).content
            response = postprocess_claude_response(response)

            # Add the feedback about stored preference
            response += f"\n\n{feedback}"

            self.chat_history.append(
                {"role": "assistant", "content": response}
            )
            return proactive_response_part + response
        elif any(trigger in message_lower for trigger in memory_triggers):
            logging.info(
                f"[{request_id}] Detected user preference recording request"
            )

            # Try to identify an appropriate label for the preference
            label = "general"
            if any(
                term in message_lower
                for term in ["busywork", "task", "suggestion"]
            ):
                label = "busywork"
            elif any(
                term in message_lower for term in ["inbox", "email", "message"]
            ):
                label = "inbox_management"
            elif any(
                term in message_lower
                for term in ["notification", "alert", "notify"]
            ):
                label = "notifications"
            elif any(
                term in message_lower
                for term in ["case stud", "example", "story"]
            ):
                label = "content_preferences"

            # Generate a summary using Claude
            try:
                summary = self.claude_client.process_query(
                    f"Summarize this user preference into a single clear sentence for memory storage: {message}",
                    self.system_message,
                    request_id=request_id,
                    model=self.claude_client.prep_model,
                )
                # Use original message as fallback if summary generation fails
                content = (
                    summary
                    if summary and len(summary) < len(message)
                    else message
                )
                logging.info(
                    f"[{request_id}] Generated preference summary: '{summary[:100]}...'"
                )
            except Exception as e:
                logging.error(
                    f"[{request_id}] Error generating preference summary: {str(e)}"
                )
                logging.error(traceback.format_exc())
                content = message
                logging.info(
                    f"[{request_id}] Using original message as preference content"
                )

            # Store the preference
            success = self.memory_store.remember_user_preference(
                label=label,
                content=content,
                source="user_clarified" if content != message else "user",
                tags=["user-preference", label],
            )

            # Log the content regardless of success for debugging
            logging.info(
                f"[{request_id}] Preference content for '{label}': {content[:50]}... (truncated)"
            )

            # Check memory store vector availability
            vector_available = getattr(
                self.memory_store, "vector_search_available", False
            )

            if success:
                if not vector_available:
                    response = f"📓 Noted your preference about **{label}** — I've saved it in basic memory (vector search unavailable)."
                    logging.info(
                        f"[{request_id}] Stored preference in basic memory only (vector search unavailable)"
                    )
                else:
                    response = f"📓 Noted your preference about **{label}** — I've added it to my notebook for future reference."
                    logging.info(
                        f"[{request_id}] Successfully stored user preference about {label}"
                    )
            else:
                response = f"⚠️ I couldn't store your preference about **{label}**, but I've logged the message."
                logging.error(
                    f"[{request_id}] Failed to store user preference"
                )
                response += "\nYou can rephrase your preference if you'd like me to try saving it again."

            self.chat_history.append(
                {"role": "assistant", "content": response}
            )
            return proactive_response_part + response

        if (
            "search the last 3 months" in message_lower
            or "enrich memory" in message_lower
            or "enrich notebook" in message_lower
        ):
            logging.info(
                f"[{request_id}] Autonomous memory enrichment task trigger detected. Initiating."
            )
            self.memory_actions_handler.perform_autonomous_memory_enrichment(
                request_id=request_id
            )
            response = "I've initiated a memory enrichment process. You can continue interacting with me."
            self.chat_history.append(
                {"role": "assistant", "content": response}
            )
            return proactive_response_part + response

            # try: # Commenting out the orphaned try from the 'log test' block
            # Special 'log test' command for debugging API calls - Commented out to restore flow
            # if message.lower().strip() == "log test":
            #     request_id = str(uuid.uuid4())
            #     logging.info(f"[{request_id}] Received 'log test' command. Testing API logging.")
            #     try:
            #         # Example: Test logging for a simple Gmail API call (e.g., get profile)
            #         # Replace with an actual simple API call you want to test logging for.
            #         # self.gmail_client.service.users().getProfile(userId='me').execute()
            #         logging.info(f"[{request_id}] Test API call successful (simulated). Check logs.")
            #         response = f"API logging test completed. Check logs at {datetime.now().isoformat()}"
            #         self.chat_history.append({"role": "assistant", "content": response})
            #         return response
            #     except Exception as e:
            #         logging.error(
            #             f"[{request_id}] Test API call FAILED with error: {e}",
            #             exc_info=True,
            #         )
            #         response = "Log test failed due to an internal error. Please check server logs."
            #         self.chat_history.append({"role": "assistant", "content": response})
            #         return response
            # # except Exception as e_outer: # Commenting out the orphaned except from the 'log test' block
            # #     logging.critical(
            # #         f"[{request_id}] Critical error in 'log test' processing block: {e_outer}",
            # #         exc_info=True,
            # #     )
            # #     response = "An unexpected critical error occurred during the log test. Admins have been notified."
            # #     self.chat_history.append({"role": "assistant", "content": response})
            # #     return response

            # 1. Handle pending actions, especially email query confirmation
            if (
                self.pending_email_context
            ):  # Check if any pending context exists
                user_input_lower = message.lower().strip()
                pending_type = self.pending_email_context.get("type")

                AFFIRMATIVES = {
                    "yes",
                    "y",
                    "sure",
                    "okay",
                    "ok",
                    "go ahead",
                    "please do",
                    "search",
                    "yep",
                    "yeah",
                    "affirmative",
                    "do it",
                    "proceed",
                    "sounds good",
                    "correct",
                }
                # Negatives are largely handled by the general 'no' block preceding this logic,
                # but defining here for clarity if specific negative handling for a type is needed.
                # NEGATIVES = {"no", "n", "cancel", "stop", "negative", "don't", "nope"}

                if pending_type == "gmail_query_confirmation":
                    gmail_search_string = self.pending_email_context.get(
                        "gmail_query", "your previous email search"
                    )
                    original_user_message = self.pending_email_context.get(
                        "original_message"
                    )

                    # Define ambiguous responses specific to a yes/no confirmation context
                    AMBIGUOUS_FOR_CONFIRM = {
                        "maybe",
                        "not sure",
                        "hmm",
                        "hm",
                        "possibly",
                        "i'm not sure",
                        "i dont know",
                        "i don't know",
                    }

                    if user_input_lower in AFFIRMATIVES:
                        logging.info(
                            f"[{request_id}] User affirmatively confirmed pending Gmail query: {gmail_search_string[:50]}..."
                        )
                        self.pending_email_context = (
                            None  # Clear context before action
                        )

                        acknowledgement = "👍 Starting the search now..."

                        logging.critical(
                            f"[{request_id}] user-initiated search_emails using: {gmail_search_string}"
                        )
                        emails, search_results_text = (
                            self.gmail_client.search_emails(
                                query=gmail_search_string,
                                original_user_query=original_user_message,
                                system_message=self.system_message,
                                request_id=request_id,
                            )
                        )
                        if (
                            search_results_text
                            and "error" in search_results_text.lower()
                            and st
                        ):
                            st.session_state.last_gmail_error = (
                                search_results_text
                            )

                        final_response_parts = [acknowledgement]

                        if emails:
                            logging.info(
                                f"[{request_id}] Found {len(emails)} emails from confirmed search. Storing."
                            )
                            self.memory_actions_handler.store_emails_in_memory(
                                emails=emails,
                                query=original_user_message,
                                request_id=request_id,
                            )
                            email_ids = [
                                email.get("id")
                                for email in emails
                                if email.get("id")
                            ]
                            self.memory_actions_handler.record_interaction_in_memory(
                                query=original_user_message,
                                response=search_results_text
                                or f"Found {len(emails)} emails.",
                                request_id=request_id,
                                email_ids=email_ids,
                                client=None,
                            )
                            if search_results_text:
                                final_response_parts.append(
                                    search_results_text
                                )
                            else:
                                final_response_parts.append(
                                    f"I found {len(emails)} email(s) matching your search for `{gmail_search_string}`. They have been processed and stored."
                                )
                        else:
                            logging.info(
                                f"[{request_id}] No emails found for confirmed query: {gmail_search_string[:50]}"
                            )
                            if (
                                search_results_text
                            ):  # Claude might explain why no results
                                final_response_parts.append(
                                    search_results_text
                                )
                            else:  # Generic no results
                                final_response_parts.append(
                                    f"I searched for `{gmail_search_string}` but couldn't find any matching emails."
                                )

                        response = "\n\n".join(
                            filter(None, final_response_parts)
                        )

                        self.chat_history.append(
                            {"role": "assistant", "content": response}
                        )
                        return proactive_response_part + response
                    elif user_input_lower in AMBIGUOUS_FOR_CONFIRM:
                        logging.info(
                            f"[{request_id}] Ambiguous response ('{user_input_lower}') to Gmail query confirmation for '{gmail_search_string}'. Re-prompting."
                        )
                        response = f"Sorry, I didn't quite catch that. Did you want me to proceed with the search for `{gmail_search_string}`? (yes/no)"
                        # Do NOT clear self.pending_email_context here, as we are re-prompting.
                        self.chat_history.append(
                            {"role": "assistant", "content": response}
                        )
                        return proactive_response_part + response
                    else:
                        # Input is neither affirmative nor specifically ambiguous for this confirmation.
                        # It's likely a new query. Log this and allow flow to continue.
                        # The self.pending_email_context will be cleared by the generic handler below if it's still set.
                        logging.info(
                            f"[{request_id}] User input '{user_input_lower[:30]}' received during Gmail query confirmation for '{gmail_search_string[:50]}...' "
                            f"is not affirmative or specifically ambiguous for the confirmation. Will treat as new query."
                        )
                        # No 'return response' here, let it fall through to the generic pending context clearing logic that follows
                        pass

                # If pending_email_context was for a different type not handled above,
                # or if the input was not affirmative/ambiguous for gmail_query_confirmation (e.g. a new query),
                # clear the old context and proceed to classify the current message as a new query.
                # This path is taken if the input wasn't an explicit 'no' (caught earlier),
                # wasn't an affirmative to a gmail_query_confirmation, and wasn't ambiguous to it.
                logging.info(
                    f"[{request_id}] User provided new input ('{message[:20]}...') while a '{pending_type}' confirmation was pending. "
                    f"Proceeding with new input, clearing old pending context of type '{pending_type}'."
                )
                self.pending_email_context = (
                    None  # Clear old pending context before new classification
                )

            # 2. Classify the new query (or current if no pending context was handled, or if pending context was cleared)
            query_type, confidence, scores = classify_query_type(
                message, classifier=self.ml_classifier
            )
            uncertainty_message = get_classification_feedback(
                query_type, confidence
            )
            logging.info(
                f"[{request_id}] Classified query: type='{query_type}', confidence={confidence:.2f}, scores={scores}, uncertainty_feedback_provided='{bool(uncertainty_message)}'"
            )

            # 3. Handle specific query types based on classification
            if query_type == "catch_up":
                logging.info(f"[{request_id}] Handling 'catch_up' query.")
                response = self._handle_catch_up_query(request_id)

            elif (
                query_type == "clarify"
                or (query_type == "ambiguous" and confidence < 0.25)
                or query_type == "chat"
            ):
                response = self._handle_general_chat_query(
                    message, query_type, request_id
                )

            elif query_type == "triage" or (
                query_type == "ambiguous" and scores.get("triage", 0) > 0.2
            ):
                response = handle_triage_query(
                    self, message, request_id, scores
                )

            elif query_type == "email_search":
                response = handle_email_search_query(
                    self, message, message_lower, request_id
                )

            elif query_type == "notebook_lookup":
                response = self._handle_notebook_lookup_query(
                    message, request_id
                )

            elif query_type == "mixed_semantic":
                response = self._handle_mixed_semantic_query(
                    message, request_id
                )

            elif query_type == "vector_fallback" or (
                query_type == "ambiguous" and not response
            ):  # Ambiguous not caught by other specific handlers
                response = self._handle_vector_fallback_query(
                    message, query_type, confidence, request_id
                )

            # 4. Default flow / Fallback if no specific handler produced a response yet
            if not response:
                response = self._handle_unknown_or_fallback_query(
                    message, query_type, request_id
                )

                # 5. Add uncertainty warning if needed (unless it's a confirmation prompt for a pending search)
                if (
                    uncertainty_message and not self.pending_email_context
                ):  # Don't add to "Shall I proceed?"
                    response = uncertainty_message + "\n\n" + response

        classification_response = self.handle_query_classification(
            message, request_id
        )
        self.chat_history.append(
            {"role": "assistant", "content": classification_response}
        )
        logging.info(
            f"[{request_id}] Generated response (first 50 chars): {classification_response[:50]}..."
        )
        return proactive_response_part + classification_response

    def _handle_unknown_or_fallback_query(
        self, message: str, query_type_for_logging: str, request_id: str
    ) -> str:
        """Handles queries not caught by specific handlers, or 'unknown' queries.

        Tries a direct memory query first if keywords match, otherwise falls back to general Claude chat
        with preference injection and TASK_CHAIN handling.
        """
        response_str = ""
        logging.info(
            f"[{request_id}] Query type '{query_type_for_logging}' not handled by specific handlers. Trying memory or general chat."
        )

        memory_keywords = [
            "remember",
            "client info",
            "task list",
            "database status",
            "what do you know",
            "action items",
            "delegat",
            "preference",
        ]
        is_direct_memory_query = any(
            keyword in message.lower() for keyword in memory_keywords
        )

        if is_direct_memory_query:
            memory_response_text = (
                self.memory_actions_handler.handle_user_memory_query(
                    message, request_id
                )
            )
            if memory_response_text:
                response_str = memory_response_text
                # handle_user_memory_query records its own interaction

        if (
            not response_str
        ):  # If not a memory query or memory query yielded no response
            logging.info(
                f"[{request_id}] Falling back to general Claude chat for message: {message[:50]}..."
            )

            relevant_preferences = self.memory_store.find_relevant_preferences(
                message
            )
            preference_context = ""
            if relevant_preferences:
                logging.info(
                    f"[{request_id}] Found {len(relevant_preferences)} relevant preferences"
                )
                preference_context = "\n\nUSER PREFERENCES:\n"
                for pref in relevant_preferences:
                    preference_context += f"- {pref.get('label', 'general').upper()}: {pref.get('content')}\n"

            enhanced_system = self.system_message
            if preference_context:
                enhanced_system += f"\n\n{preference_context}\n\nApply these preferences when generating your response."

            claude_chat_response_text = self.claude_client.chat(
                message,
                self.chat_history[:-1],
                enhanced_system,
                request_id=request_id,
            )
            processed_chat_response = postprocess_claude_response(
                claude_chat_response_text
            )

            self.memory_actions_handler.record_interaction_in_memory(
                original_user_query=message,
                final_response=processed_chat_response,
                request_id=request_id,
                query_type="unknown_fallback_chat",
                search_method="general_claude_chat",
            )

            response_str = processed_chat_response  # Base response is the processed chat response

            if response_str.strip().startswith("TASK_CHAIN:"):
                logging.info(
                    f"[{request_id}] Claude proposed TASK_CHAIN plan: {response_str[:80]}"
                )

                try:
                    plan = parse_task_chain(response_str)
                    logging.info(
                        f"[{request_id}] Parsed TASK_CHAIN into {len(plan)} step(s)"
                    )
                except Exception as e:  # pragma: no cover - defensive
                    logging.error(
                        f"[{request_id}] Failed to parse TASK_CHAIN: {e}"
                    )
                    plan = []

                if "enrich" in response_str.lower() and any(
                    term in response_str.lower()
                    for term in ["inbox", "memory", "notebook", "email"]
                ):
                    if self.autonomous_task_counter < 3:
                        self.autonomous_task_counter += 1
                        logging.info(
                            f"[{request_id}] Auto-executing memory enrichment (step {self.autonomous_task_counter}/3)"
                        )
                        self.memory_actions_handler.perform_autonomous_memory_enrichment(
                            request_id=request_id
                        )
                        response_str = (
                            "I've initiated an autonomous memory enrichment process "
                            "based on the current context. You can continue interacting."
                        )
                    else:
                        logging.info(
                            f"[{request_id}] Pausing after 3 autonomous searches, asking user for confirmation"
                        )
                        self.pending_email_context = {
                            "original_message": message,
                            "gmail_query": "TASK_CHAIN",
                            "plan": plan,
                            "type": "task_chain_confirmation",
                        }
                        response_str += (
                            f"\n\nI've done {self.autonomous_task_counter} steps. "
                            "Would you like me to keep going?"
                        )
                else:
                    if (
                        plan
                        and st
                        and st.session_state.get("agentic_mode_enabled")
                    ):
                        st.session_state.agentic_plan = plan
                        st.session_state.agentic_state = {
                            "current_step_index": 0,
                            "executed_call_count": 0,
                            "accumulated_results": {},
                            "error_messages": [],
                        }
                        logging.info(
                            f"[{request_id}] Executing parsed plan automatically"
                        )
                        try:  # Delayed import to avoid circular dependency
                            from chat_app_st import run_agentic_plan  # type: ignore

                            run_agentic_plan()
                        except Exception as e:  # pragma: no cover - defensive
                            logging.error(
                                f"[{request_id}] Error running agentic plan: {e}"
                            )
                        response_str = "Okay, I'm starting that task chain."
                    else:
                        self.pending_email_context = {
                            "original_message": message,
                            "gmail_query": "TASK_CHAIN",
                            "plan": plan,
                            "type": "task_chain_confirmation",
                        }
                        logging.info(
                            f"[{request_id}] Parsed plan queued for confirmation"
                        )
                        response_str += "\n\nWould you like me to proceed with this multi-step task?"
        return response_str

    def get_email_by_id(
        self,
        email_id: str,
        user_query: str = "",
        request_id: str | None = None,
    ) -> str:
        if not self.gmail_client:
            return "Gmail client not available."
        email_data, msg = self.gmail_client.get_email_by_id(
            email_id, user_query
        )
        if msg and "error" in msg.lower() and st:
            st.session_state.last_gmail_error = msg
        if email_data:
            try:
                self.memory_actions_handler.store_emails_in_memory(
                    emails=[email_data],
                    query=user_query or email_id,
                    request_id=request_id or str(uuid.uuid4()),
                )
            except Exception:
                pass
        return msg

    def run(self) -> None:
        """Run the Gmail Chatbot application with GUI."""
        self.gui = None
        try:
            # Initialize GUI with callback to process messages
            self.gui = EmailChatbotGUI(self.process_message)

            # Display welcome message
            welcome_message = (
                "Welcome to the Gmail Chatbot Assistant! I can help you interact with your Gmail account. "
                "You can ask me to find emails, summarize them, or extract specific information. "
                "For example, try asking:\n"
                "- Find emails from John about the project meeting\n"
                "- Show me my recent emails about budget approvals\n"
                "- Find emails with attachments sent last week\n"
                "I'll use Claude to help process your requests and present the information in a clear, concise manner."
            )
            self.gui.display_message("Assistant", welcome_message)

            # Run GUI (this will block until GUI is closed)
            self.gui.run()

        except Exception as e:
            safe_log("error", f"Error running application: {e}")
            print(f"Error: {str(e)}")
        finally:
            # Ensure GUI resources are properly cleaned up
            print("[INFO] Application is shutting down...")

            # 1. Manually shutdown logging system FIRST
            try:
                shutdown_logging()
                print("[INFO] Logging system shut down cleanly.")
            except Exception as e:
                print(f"[ERROR] Logging shutdown failed: {e}")

            if self.gui is not None:
                try:
                    # safe_log('info', "Closing GUI resources") # Cannot log here, logging is off
                    print("[INFO] Closing GUI resources (logging is off).")
                    self.gui.close()
                except Exception as cleanup_error:
                    print(
                        f"[ERROR] Error during GUI cleanup: {str(cleanup_error)}"
                    )

            # Give background threads a chance to complete
            wait_for_threads(timeout=2)
