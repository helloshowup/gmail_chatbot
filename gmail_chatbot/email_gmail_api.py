#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import os
import base64
import pickle
import logging
import ssl
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from email.mime.text import MIMEText

import google.auth.exceptions
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from gmail_chatbot.email_config import GMAIL_SCOPES, GMAIL_CLIENT_SECRET_FILE, GMAIL_TOKEN_FILE, \
    DATA_DIR, MAX_EMAILS_PER_SEARCH, MAX_EMAIL_BODY_CHARS
from gmail_chatbot.email_claude_api import ClaudeAPIClient
from gmail_chatbot.api_logging import log_gmail_request, log_gmail_response

# Configure logging
logger = logging.getLogger(__name__)
logger.debug("email_gmail_api module loaded")

class GmailAPIClient:
    """Client for interacting with Gmail API with Claude assistance."""
    
    def __init__(self, claude_client: ClaudeAPIClient, system_message: str) -> None:
        """Initialize the Gmail API client with Claude assistance.
        
        Args:
            claude_client: Instance of ClaudeAPIClient for processing
            system_message: System message for Claude API
        """
        self.claude = claude_client
        self.system_message = system_message
        self.service = self._authenticate()
        self.user_id = 'me'  # Default Gmail API user ID for authenticated user
        
    def test_connection(self) -> Dict[str, Any]:
        """Test connection to Gmail API with a lightweight API call.
        
        Returns:
            Dict containing success status and additional information
        """
        try:
            # Make a lightweight call to get profile info
            # This only returns basic account info without accessing any emails
            profile = self.service.users().getProfile(userId=self.user_id).execute()
            
            # Verify we got a valid response with expected fields
            if profile and 'emailAddress' in profile:
                return {
                    'success': True,
                    'message': f"Connected to Gmail API for {profile['emailAddress']}",
                    'email': profile['emailAddress'],
                    'timestamp': datetime.now().isoformat()
                }
            else:
                return {
                    'success': False,
                    'message': "Gmail API responded but returned unexpected data",
                    'data': profile
                }
                
        except google.auth.exceptions.RefreshError as e:
            logger.error(f"Authentication token refresh failed: {e}")
            return {
                'success': False, 
                'message': f"Authentication token expired or invalid: {e}",
                'error_type': 'auth_refresh_error'
            }
            
        except google.auth.exceptions.GoogleAuthError as e:
            logger.error(f"Google authentication error: {e}")
            return {
                'success': False,
                'message': f"Google authentication error: {e}",
                'error_type': 'auth_error'
            }
            
        except googleapiclient.errors.HttpError as e:
            logger.error(f"Gmail API HTTP error: {e}")
            return {
                'success': False,
                'message': f"Gmail API error: {e}",
                'error_type': 'api_error',
                'status_code': e.resp.status if hasattr(e, 'resp') else None
            }
            
        except ssl.SSLError as e_ssl:
            logger.error(f"Gmail API SSL error during test_connection: {e_ssl}")
            return {
                'success': False,
                'message': f"Gmail API SSL error: {str(e_ssl)}. Please check your internet connection, firewall, or proxy settings. The system's date/time might also be incorrect.",
                'error_type': 'ssl_error'
            }
            
        except Exception as e:
            logger.error(f"Unexpected error testing Gmail API connection: {e}", exc_info=True)
            return {
                'success': False,
                'message': f"Unexpected error: {e}",
                'error_type': 'unknown_error'
            }
        
    def _authenticate(self) -> Any:
        """Authenticate with Gmail API using OAuth2.
        
        Returns:
            Gmail API service object
        """
        creds = None
        token_path = DATA_DIR / GMAIL_TOKEN_FILE

        # Load credentials from token.json if it exists
        if os.path.exists(token_path):
            with open(token_path, 'rb') as token:
                try:
                    creds = pickle.load(token)
                except Exception as e:
                    logger.error(f"Error loading token file: {e}")
        else: # Corresponds to 'if os.path.exists(token_path):'
            pass

        # Check if credentials are valid or need refresh
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except ssl.SSLError as e_ssl:
                    logger.error(f"SSL Error during credential refresh: {e_ssl}")
                    raise ValueError(f"SSL Error refreshing credentials: {str(e_ssl)}. Please check your internet connection, firewall, or proxy settings.")
                except google.auth.exceptions.RefreshError as e:
                    logger.error(f"Error refreshing credentials: {e}. Attempting re-authentication.")
                    creds = None # Force re-authentication by nullifying creds
            
            # If no valid credentials, need to authenticate
            if not creds:
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        DATA_DIR / GMAIL_CLIENT_SECRET_FILE, GMAIL_SCOPES)
                    creds = flow.run_local_server(port=0)
                except Exception as e:
                    logger.error(f"Error during authentication flow: {e}")
                    raise ValueError(f"Authentication failed: {str(e)}")
            
            # Save the credentials for the next run
            with open(token_path, 'wb') as token:
                pickle.dump(creds, token)
        
        try:
            # Build the Gmail API service
            service = build('gmail', 'v1', credentials=creds)
            logger.info("Successfully authenticated with Gmail API")
            return service
        except ssl.SSLError as e_ssl:
            logger.error(f"SSL Error building Gmail service: {e_ssl}")
            raise ValueError(f"SSL Error building Gmail service: {str(e_ssl)}. Please check your internet connection, firewall, or proxy settings. The system's date/time might also be incorrect.")
        except Exception as e:
            logger.error(f"Error building Gmail service: {e}")
            raise ValueError(f"Failed to build Gmail service: {str(e)}")
    
    def _extract_gmail_search_query(self, claude_response: str) -> str:
        """Extract the actual Gmail search query from Claude's response.
        
        This function attempts to extract a valid Gmail search query from Claude's
        narrative response by looking for specific patterns like backticks, 
        "after:" or "before:" date specifiers, or other common Gmail search operators.
        
        Args:
            claude_response: The full response from Claude
            
        Returns:
            The extracted Gmail search query or a default query if none found
        """
        import re
        
        # Look for text within backticks which often contains the actual search query
        backtick_pattern = r'`([^`]+)`'
        backtick_matches = re.findall(backtick_pattern, claude_response)
        
        if backtick_matches:
            for match in backtick_matches:
                # If the backtick content contains common Gmail search operators, use it
                if re.search(r'(after:|before:|from:|to:|subject:|in:|is:|has:|newer:|older:)', match):
                    logger.info(f"Extracted Gmail search query from backticks: {match}")
                    return match
        
        # Look for date-based queries which are common in email searches
        date_pattern = r'(after:\s*\d{4}/\d{1,2}/\d{1,2}\s*before:\s*\d{4}/\d{1,2}/\d{1,2})'
        date_matches = re.findall(date_pattern, claude_response)
        if date_matches:
            logger.info(f"Extracted date-based Gmail search query: {date_matches[0]}")
            return date_matches[0]
        
        # Look for common Gmail search operators in the text
        search_patterns = [
            # Date patterns
            r'(after:\s*\d{4}/\d{1,2}/\d{1,2})',
            r'(before:\s*\d{4}/\d{1,2}/\d{1,2})',
            r'(newer_than:\s*\d+d)',
            r'(older_than:\s*\d+d)',
            # Sender/recipient patterns
            r'(from:\s*[\w.-]+@[\w.-]+)',
            r'(to:\s*[\w.-]+@[\w.-]+)',
            # Content patterns
            r'(subject:\s*"[^"]+")',
            r'(has:\s*attachment)',
            r'(has:\s*attachment\s+filename:\s*[\w.-]+)'
        ]
        
        for pattern in search_patterns:
            matches = re.findall(pattern, claude_response)
            if matches:
                # Join multiple search parameters if found
                search_query = " ".join(matches)
                logger.info(f"Extracted Gmail search query using patterns: {search_query}")
                return search_query
        
        # If we're looking for today's emails specifically
        if "today" in claude_response.lower():
            from datetime import datetime, timedelta
            today = datetime.now().strftime("%Y/%m/%d")
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y/%m/%d")
            query = f"after:{today} before:{tomorrow}"
            logger.info(f"Generated today's date query: {query}")
            return query
            
        # Fall back to a simple query based on the original question
        # Just use the last 3 days as a reasonable default
        from datetime import datetime, timedelta
        three_days_ago = (datetime.now() - timedelta(days=3)).strftime("%Y/%m/%d")
        today = datetime.now().strftime("%Y/%m/%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y/%m/%d")  # Define tomorrow here too
        fallback_query = f"after:{three_days_ago} before:{tomorrow}"
        logger.warning(f"Could not extract specific search query from Claude response. Using fallback: {fallback_query}")
        return fallback_query
        
    def search_emails(self, query: str, original_user_query: Optional[str] = None, system_message: Optional[str] = None, request_id: Optional[str] = None) -> Tuple[List[Dict[str, Any]], str]:
        """Search emails using Gmail API.
        
        Args:
            query: Gmail search query or Claude's response containing a search query
            original_user_query: Original user natural language query (for Claude)
            system_message: System message for Claude
            request_id: Optional unique ID to trace this request through the chain
            
        Returns:
            Tuple of (list of emails, Claude's response)
        """
        try:
            # Store the original Claude response for later use
            claude_response = query
            
            # Check if query contains an error message from Claude
            if query.startswith('ERROR:'):
                logger.error(f"[{request_id if request_id else 'NO_ID'}] Received error query from Claude: {query}")
                return [], "I'm sorry, I encountered an error while trying to search your emails. Could you please rephrase your question?"
            
            # Extract the actual Gmail search query from Claude's response
            extracted_query = self._extract_gmail_search_query(query)
            
            # Log the Gmail API request (both original and extracted)
            request_log_path = log_gmail_request(extracted_query, original_user_query, request_id)
            
            # Log detailed information about this search operation
            logger.info(f"[{request_id if request_id else 'NO_ID'}] Original Claude response: '{query[:100]}...'")
            logger.info(f"[{request_id if request_id else 'NO_ID'}] Extracted Gmail search query: '{extracted_query}'")
            logger.critical(f"search_emails using extracted query: {extracted_query}") # This will appear in both terminal and log file
            
            # Call Gmail API to search for messages with the extracted query
            try:
                results = self.service.users().messages().list(userId='me', q=extracted_query, maxResults=MAX_EMAILS_PER_SEARCH).execute()
                messages = results.get('messages', [])
            except ssl.SSLError as e_ssl:
                logger.error(f"[{request_id if request_id else 'NO_ID'}] SSL Error during email search (list operation): {e_ssl}")
                return [], f"SSL Error during email search: {str(e_ssl)}. Please check your internet connection, firewall, or proxy settings. The system's date/time might also be incorrect."
            
            if not messages:
                logger.info("No emails found matching the query")
                # Log the empty response
                log_gmail_response(
                    request_log_path=request_log_path,
                    email_count=0,
                    email_metadata=[]
                )
                return [], "No emails found matching your query."
                
            logger.info(f"Found {len(messages)} emails matching the query")
            
            # Get full message details for each message
            email_data = []
            
            # Anti-hallucination safeguard: Ensure Gmail API actually returned real messages
            if not isinstance(messages, list) or len(messages) == 0 or not all(isinstance(m, dict) and 'id' in m for m in messages):
                logger.warning(f"Invalid or empty message format returned by Gmail API: {messages}")
                return [], "No valid emails found matching your query. The search returned an invalid format."

            for message in messages:
                msg_id = message['id']
                
                # Get the full message
                try:
                    msg = self.service.users().messages().get(userId='me', id=msg_id).execute()
                except ssl.SSLError as e_ssl:
                    logger.error(f"[{request_id if request_id else 'NO_ID'}] SSL Error fetching details for email ID {msg_id}: {e_ssl}. Skipping this email.")
                    continue
                except HttpError as error_get:
                    logger.error(f"[{request_id if request_id else 'NO_ID'}] Gmail API HTTP error for email ID {msg_id}: {error_get}. Skipping this email.")
                    continue
                except Exception as e_get:
                    logger.error(f"[{request_id if request_id else 'NO_ID'}] Unexpected error fetching details for email ID {msg_id}: {e_get}. Skipping this email.")
                    continue
                
                # Extract relevant message data
                headers = {header['name']: header['value'] for header in msg['payload']['headers']}
                body_info = self._get_email_body(msg, truncate=True)
                
                email_info = {
                    'id': msg['id'],
                    'threadId': msg['threadId'],
                    'labelIds': msg.get('labelIds', []),
                    'snippet': msg.get('snippet', ''),
                    'subject': headers.get('Subject', 'No Subject'),
                    'from': headers.get('From', 'Unknown Sender'),
                    'to': headers.get('To', 'Unknown Recipient'),
                    'date': headers.get('Date', 'Unknown Date'),
                    'body': body_info['body'],
                    'truncated': body_info['truncated'],
                    'full_length': body_info['full_length']
                }
                
                email_data.append(email_info)
            
            # Log the Gmail API response
            log_gmail_response(
                request_log_path=request_log_path,
                email_count=len(email_data),
                email_metadata=email_data
            )

            # Process email data through Claude if system_message is provided
            if system_message and self.claude:
                claude_response = self.claude.process_email_content(
                    email_data,
                    original_user_query,
                    system_message,
                    model=self.claude.prep_model,
                )
                return email_data, claude_response
            else:
                # Return raw email data without processing
                return email_data, ""
        
        except ssl.SSLError as e_ssl: # Should be caught by the specific try-except for the list call, but as a fallback
            logger.error(f"[{request_id if request_id else 'NO_ID'}] Uncaught SSL Error in search_emails: {e_ssl}")
            return [], f"An unexpected SSL error occurred: {str(e_ssl)}. Please check logs."
        except HttpError as error:
            logger.error(f"[{request_id if request_id else 'NO_ID'}] Gmail API HTTP error in search_emails: {error}")
            return [], f"Error accessing your emails: {str(error)}"
        except Exception as e:
            logger.error(f"[{request_id if request_id else 'NO_ID'}] Error searching emails: {e}")
            return [], f"Error searching your emails: {str(e)}"
    
    def get_email_by_id(self, email_id: str, user_query: str = "") -> Tuple[Optional[Dict[str, Any]], str]:
        """Get a specific email by ID and process through Claude.
        
{{ ... }}
            email_id: Gmail message ID
            user_query: Original user query for context (optional)
            
        Returns:
            Tuple of (email data, formatted response)
        """
        try:
            # Log the Gmail API request
            request_log_path = log_gmail_request(
                query=f"id:{email_id}",
                original_user_query=f"Get email with ID {email_id}"
            )
            
            # Get the email from Gmail API
            try:
                msg = self.service.users().messages().get(
                    userId=self.user_id, id=email_id, format='full'
                ).execute()
            except ssl.SSLError as e_ssl:
                logger.error(f"SSL Error retrieving email ID {email_id}: {e_ssl}")
                return None, f"SSL Error retrieving email {email_id}: {str(e_ssl)}. Please check your internet connection, firewall, or proxy settings. The system's date/time might also be incorrect."
            
            # Extract relevant message data
            headers = {header['name']: header['value'] for header in msg['payload']['headers']}
            body_info = self._get_email_body(msg, truncate=True)
            
            email_info = {
                'id': msg['id'],
                'threadId': msg['threadId'],
                'labelIds': msg.get('labelIds', []),
                'snippet': msg.get('snippet', ''),
                'subject': headers.get('Subject', 'No Subject'),
                'from': headers.get('From', 'Unknown Sender'),
                'to': headers.get('To', 'Unknown Recipient'),
                'date': headers.get('Date', 'Unknown Date'),
                'body': body_info['body'],
                'truncated': body_info['truncated'],
                'full_length': body_info['full_length']
            }
            
            # Log the Gmail API response
            log_gmail_response(
                request_log_path=request_log_path,
                email_count=1,
                email_metadata=[email_info]
            )
            
            # Process email data through Claude for user-friendly response
            if user_query:
                response = self.claude.process_email_content(
                    email_info,
                    user_query,
                    self.system_message,
                    model=self.claude.prep_model,
                )
            else:
                response = self.claude.process_email_content(
                    email_info,
                    "Summarize this email and extract key information",
                    self.system_message,
                    model=self.claude.prep_model,
                )
            
            return email_info, response
            
        except ssl.SSLError as e_ssl: # Should be caught by the specific try-except above, but as a fallback
            logger.error(f"Uncaught SSL Error in get_email_by_id for email ID {email_id}: {e_ssl}")
            return None, f"An unexpected SSL error occurred while retrieving email {email_id}: {str(e_ssl)}. Please check logs."
        except HttpError as error:
            logger.error(f"Gmail API HTTP error for email ID {email_id}: {error}")
            return None, f"Error accessing email {email_id}: {str(error)}"
        except Exception as e:
            logger.error(f"Error getting email ID {email_id}: {e}", exc_info=True)
            return None, f"Error retrieving email {email_id}: {str(e)}"
    
    def _get_email_body(self, message: Dict[str, Any], truncate: bool = True) -> Dict[str, Any]:
        """Extract the email body from the message payload.
        
        Args:
{{ ... }}
            truncate: Whether to truncate the body to conserve tokens
            
        Returns:
            Dictionary with email body text and metadata
        """
        full_body = ""
        
        # Extract body from payload parts (multipart emails)
        if 'parts' in message['payload']:
            for part in message['payload']['parts']:
                if part['mimeType'] == 'text/plain' and 'data' in part['body']:
                    body_data = part['body']['data']
                    full_body += base64.urlsafe_b64decode(body_data).decode('utf-8', errors='replace')
        
        # Extract body from single-part emails
        elif 'body' in message['payload'] and 'data' in message['payload']['body']:
            body_data = message['payload']['body']['data']
            full_body = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='replace')
        
        # Fallback to snippet if body is empty
        if not full_body and 'snippet' in message:
            full_body = message['snippet']
            
        # Prepare result with metadata
        result = {
            'full_length': len(full_body),
            'truncated': truncate and len(full_body) > MAX_EMAIL_BODY_CHARS,
            'body': full_body[:MAX_EMAIL_BODY_CHARS] if truncate and len(full_body) > MAX_EMAIL_BODY_CHARS else full_body
        }
        
        # Add truncation notice if applicable
        if result['truncated']:
            truncation_percent = int((len(full_body) - MAX_EMAIL_BODY_CHARS) / len(full_body) * 100)
            result['body'] += f"\n\n[...{truncation_percent}% of message truncated to conserve tokens. Full content available on request...]"
            logger.info(f"Truncated email body from {result['full_length']} to {MAX_EMAIL_BODY_CHARS} chars ({truncation_percent}% reduction)")

        return result

    def send_email(self, to: str, subject: str, body: str) -> Dict[str, Any]:
        """Send an email using the Gmail API.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            body: Plain text body of the email.

        Returns:
            Dictionary with the API response or error details.
        """
        message = MIMEText(body)
        message['to'] = to
        message['subject'] = subject

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

        try:
            sent = self.service.users().messages().send(
                userId=self.user_id,
                body={'raw': raw_message}
            ).execute()
            logger.info(f"Sent email to {to} with subject '{subject}'")
            return {"status": "success", "data": sent}
        except ssl.SSLError as e_ssl:
            logger.error(f"SSL Error sending email: {e_ssl}")
            return {"status": "failure", "error": f"SSL Error: {e_ssl}"}
        except HttpError as error:
            logger.error(f"HTTP error sending email: {error}")
            return {"status": "failure", "error": f"HTTP Error: {error}"}
        except Exception as e:
            logger.error(f"Unexpected error sending email: {e}")
            return {"status": "failure", "error": str(e)}
