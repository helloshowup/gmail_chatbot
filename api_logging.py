#!/usr/bin/env python3
# -*- coding: utf-8 -*-

print("Loading API logging module with path: C:\\Users\\User\\Documents\\showup-v4\\logs\\gmail_chatbot_api")

import os
import sys
import json
import logging
import traceback
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

# Setup direct console output for critical errors
def log_critical(message):
    print(f"CRITICAL API LOGGING ERROR: {message}", file=sys.stderr)
    sys.stderr.flush()  # Force immediate output
    logging.critical(f"API LOGGING ERROR: {message}")

# Import configuration with error handling and fail-safe fallbacks
try:
    # Get the project root directory
    try:
        from pathlib import Path
        file_path = os.path.dirname(os.path.abspath(__file__))
        project_root = Path(file_path).parent.parent
        logs_dir_base = project_root / "logs"
        fallback_logs_dir = logs_dir_base / "gmail_chatbot_api"
        print(f"Determined fallback logs directory: {fallback_logs_dir}")
    except Exception as e:
        log_critical(f"Error determining fallback logs directory: {e}")
        fallback_logs_dir = Path("logs") / "gmail_chatbot_api"  # Last resort fallback to local directory
    
    # Try to import from config
    from email_config import API_LOGS_DIR
    log_dir = API_LOGS_DIR
    print(f"Loaded API_LOGS_DIR from config: {API_LOGS_DIR}")
    
    # Verify log directory exists
    if not os.path.exists(API_LOGS_DIR):
        try:
            os.makedirs(API_LOGS_DIR, exist_ok=True)
            print(f"Created API logs directory: {API_LOGS_DIR}")
        except Exception as e:
            log_critical(f"Failed to create configured logs directory: {e}")
            log_critical(f"Falling back to alternative logs directory: {fallback_logs_dir}")
            API_LOGS_DIR = fallback_logs_dir
            try:
                os.makedirs(API_LOGS_DIR, exist_ok=True)
                print(f"Created fallback API logs directory: {API_LOGS_DIR}")
            except Exception as e2:
                log_critical(f"Failed to create fallback logs directory: {e2}")
                traceback.print_exc()
                API_LOGS_DIR = Path(".") / "logs"  # Absolute last resort - local directory
                try:
                    os.makedirs(API_LOGS_DIR, exist_ok=True)
                    print(f"Created last resort logs directory: {API_LOGS_DIR}")
                except Exception:
                    log_critical("Failed to create any logs directory. Logging may fail.")
    
    # Test write permission to chosen log directory - skip this if previous steps failed
    try:
        test_file_path = Path(API_LOGS_DIR) / "test_write_permission.txt"
        with open(test_file_path, 'w') as f:
            f.write("Testing write permissions")
        os.remove(test_file_path)
        print(f"Verified write permissions for logs directory: {API_LOGS_DIR}")
    except Exception as e:
        log_critical(f"No write permission for logs directory: {e}")
        # Don't traceback, just log the issue
        log_critical("API logging to files will be disabled")
        
except ImportError as e:
    log_critical(f"Failed to import API_LOGS_DIR from email_config: {e}")
    API_LOGS_DIR = fallback_logs_dir
    print(f"Using fallback API_LOGS_DIR: {API_LOGS_DIR}")
    try:
        os.makedirs(API_LOGS_DIR, exist_ok=True)
        print(f"Created fallback logs directory after import error: {API_LOGS_DIR}")
    except Exception as e2:
        log_critical(f"Failed to create fallback logs directory: {e2}")

# Configure module logger
logger = logging.getLogger(__name__)

def ensure_log_directory_exists() -> None:
    """
    Ensures the API logs directory and current date subdirectory exist and are writable.
    Creates them if they don't exist.
    
    Raises:
        RuntimeError: If directories can't be created or aren't writable
    """
    try:
        print(f"[INFO] Ensuring log directory exists: {API_LOGS_DIR}")
        
        # Check and create main logs directory
        if not os.path.exists(API_LOGS_DIR):
            os.makedirs(API_LOGS_DIR, exist_ok=True)
            print(f"[INFO] Created main logs directory: {API_LOGS_DIR}")
            
        # Check and create date-specific subdirectory
        date_folder = os.path.join(API_LOGS_DIR, datetime.now().strftime('%Y%m%d'))
        os.makedirs(date_folder, exist_ok=True)
        print(f"[INFO] Ensured date folder exists: {date_folder}")
        
        # Verify write permissions with test file
        test_file_path = os.path.join(date_folder, "write_test.txt")
        try:
            with open(test_file_path, 'w') as f:
                f.write("Testing write permissions")
            os.remove(test_file_path)
            print("[OK] Write permissions verified for log directories")
        except Exception as e:
            error_msg = f"[X] Cannot write to log directory: {e}"
            print(error_msg)
            logging.error(error_msg)
            raise RuntimeError(f"Cannot write to log directory: {e}")
            
    except Exception as e:
        error_msg = f"[X] Failed to ensure log directories: {e}"
        print(error_msg)
        traceback.print_exc()
        logging.error(error_msg)
        raise

def log_api_interaction(interaction_type: str, 
                      request_data: Optional[Dict[str, Any]] = None,
                      response_data: Optional[Dict[str, Any]] = None,
                      query: Optional[str] = None,
                      error: Optional[str] = None) -> str:
    """
    Logs an API interaction (request and/or response) to a timestamped JSON file.
    
    Args:
        interaction_type: Type of interaction (e.g., "claude_request", "gmail_response")
        request_data: Request data to log
        response_data: Response data to log
        query: User query that initiated this interaction
        error: Error message if the interaction failed
        
    Returns:
        Path to the log file that was created
    """
    try:
        print(f" [API LOGGING] Starting log_api_interaction for type: {interaction_type}")
        
        # Ensure log directory exists
        ensure_log_directory_exists()
        print(f" [API LOGGING] Log directory verified at: {API_LOGS_DIR}")
        
        # Generate timestamp and log ID
        timestamp = datetime.now().isoformat()
        log_id = f"{interaction_type}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        print(f" [API LOGGING] Created log ID: {log_id}")
        
        # Create data structure
        data = {
            "timestamp": timestamp,
            "interaction_type": interaction_type,
            "query": query,
            "request": request_data,
            "response": response_data,
            "error": error
        }
        
        # Create date-specific folder
        date_folder = os.path.join(API_LOGS_DIR, datetime.now().strftime('%Y%m%d'))
        os.makedirs(date_folder, exist_ok=True)
        
        # Define log file path
        log_path = os.path.join(date_folder, f"{log_id}.json")
        print(f" [API LOGGING] Writing to log file: {log_path}")
        
        # Write JSON to file
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        
        print(f"[OK] [API LOGGING] Successfully logged API interaction to: {log_path}")
        
        # Verify the file was actually created
        if os.path.exists(log_path):
            file_size = os.path.getsize(log_path)
            print(f"[OK] [API LOGGING] Confirmed log file exists: {log_path} (Size: {file_size} bytes)")
        else:
            print(f"[WARNING] [API LOGGING] WARNING: Log file not found after writing: {log_path}")
        
        return log_path
    
    except Exception as e:
        error_msg = f"[X] [API LOGGING] CRITICAL ERROR logging API interaction: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        logging.error(error_msg)
        
        # Fail fast - we want to see these errors immediately
        raise

def log_claude_request(model: str, 
                      system_message: str, 
                      user_message: str,
                      original_query: str,
                      request_id: Optional[str] = None) -> str:
    """Log a request to Claude API.
    
    Args:
        model: Claude model being used
        system_message: System message for Claude
        user_message: User message sent to Claude
        original_query: Original query from the user
        request_id: Optional unique ID to trace this request through the chain
        
    Returns:
        Path to the log file
    """
    try:
        print(f"[INFO] CLAUDE API REQUEST LOGGING STARTED at {datetime.now().isoformat()}")
        print(f"[INFO] Logging Claude API request for query: {original_query[:50]}...")
        ensure_log_directory_exists()
        
        timestamp = datetime.now().isoformat()
        log_id = f"claude_request_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        data = {
            "timestamp": timestamp,
            "query": original_query,
            "original_user_query": original_query,
            "request_id": request_id,  # Track request_id for chain tracking
            "system_message": system_message,
            "user_message": user_message
        }
        
        date_folder = os.path.join(API_LOGS_DIR, datetime.now().strftime('%Y%m%d'))
        os.makedirs(date_folder, exist_ok=True)
        
        log_path = os.path.join(date_folder, f"{log_id}.json")
        print(f"[INFO] Writing Claude request log to: {log_path}")
        
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        
        print(f"[OK] Successfully logged Claude API request: {log_path}")
        return log_path
    except Exception as e:
        error_msg = f"[X] ERROR logging Claude request: {e}"
        print(error_msg)
        traceback.print_exc()
        logging.error(error_msg)
        # Fail fast - raise the exception to make errors visible
        raise

def log_claude_response(request_log_path: str, 
                        response_content: str, 
                        tokens_used: Optional[Dict[str, Any]] = None,
                        error: Optional[str] = None) -> str:
    """Logs a Claude API response after it's received.
    
    Args:
        request_log_path: Path to the request log file
        response_content: Content returned by Claude
        tokens_used: Token usage information and metadata (including request_id)
        error: Error message if the API call failed
        
    Returns:
        Path to the log file that was created
    """
    try:
        print(f"[INFO] CLAUDE API RESPONSE LOGGING STARTED at {datetime.now().isoformat()}")
        print(f"[INFO] Logging Claude API response for length: {len(response_content)}")
        ensure_log_directory_exists()
        
        response_data = {
            "content": response_content,
            "tokens": tokens_used,
            "related_request": request_log_path
        }
        
        print("[INFO] About to call log_api_interaction for claude_response")
        log_path = log_api_interaction(
            interaction_type="claude_response",
            request_data={"related_request": request_log_path},
            response_data=response_data,
            error=error
        )
        print(f"[OK] Successfully logged Claude API response to: {log_path}")
        return log_path
    except Exception as e:
        error_msg = f"[X] ERROR logging Claude response: {e}"
        print(error_msg)
        traceback.print_exc()
        logging.error(error_msg)
        # Don't raise here as it might interrupt the main workflow
        return ""

def log_gmail_request(query: str, original_user_query: Optional[str] = None, request_id: Optional[str] = None) -> str:
    """Logs a Gmail API search request.
    
    Args:
        query: Gmail search query
        original_user_query: Original user query that prompted this search
        request_id: Optional unique ID to trace this request through the chain
        
    Returns:
        Path to the log file that was created
    """
    try:
        print(f"[INFO] GMAIL API REQUEST LOGGING STARTED at {datetime.now().isoformat()}")
        print(f"[INFO] Logging Gmail API request with query: {query[:50]}...")
        ensure_log_directory_exists()
        
        request_data = {
            "gmail_query": query,
            "original_user_query": original_user_query,
            "request_id": request_id
        }
        
        return log_api_interaction(
            interaction_type="gmail_request",
            request_data=request_data,
            query=original_user_query
        )
    except Exception as e:
        error_msg = f"[X] ERROR logging Gmail request: {e}"
        print(error_msg)
        traceback.print_exc()
        logging.error(error_msg)
        # Fail fast - raise the exception to make errors visible
        raise

def log_gmail_response(request_log_path: str, 
                      email_count: int,
                      email_metadata: List[Dict[str, Any]],
                      error: Optional[str] = None,
                      request_id: Optional[str] = None) -> str:
    """Logs a Gmail API search response.
    
    Args:
        request_log_path: Path to the request log file
        email_count: Number of emails found
        email_metadata: Metadata about found emails (without full bodies)
        error: Error message if the API call failed
        request_id: Optional unique ID to trace this request through the chain
        
    Returns:
        Path to the log file that was created
    """
    try:
        print(f"[INFO] GMAIL API RESPONSE LOGGING STARTED at {datetime.now().isoformat()}")
        print(f"[INFO] Logging Gmail API response with {email_count} emails found.")
        ensure_log_directory_exists()
        
        # Create simplified email metadata without full bodies to keep logs manageable
        simplified_metadata = []
        for email in email_metadata:
            # Create a copy without the body field
            email_copy = {k: v for k, v in email.items() if k != 'body'}
            # Add truncated snippet of body if available
            if 'body' in email and email['body']:
                email_copy['body_preview'] = email['body'][:150] + '...' if len(email['body']) > 150 else email['body']
            simplified_metadata.append(email_copy)
        
        response_data = {
            "email_count": email_count,
            "emails": simplified_metadata,
            "related_request": request_log_path,
            "request_id": request_id
        }
        
        return log_api_interaction(
            interaction_type="gmail_response",
            request_data={"related_request": request_log_path},
            response_data=response_data,
            error=error
        )
    except Exception as e:
        error_msg = f"[X] ERROR logging Gmail response: {e}"
        print(error_msg)
        traceback.print_exc()
        logging.error(error_msg)
        # Fail fast - raise the exception to make errors visible
        raise
    response_data = {
        "email_count": email_count,
        "emails": simplified_metadata,
        "related_request": request_log_path
    }
    
    return log_api_interaction(
        interaction_type="gmail_response",
        request_data={"related_request": request_log_path},
        response_data=response_data,
        error=error
    )
