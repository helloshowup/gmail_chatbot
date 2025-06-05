#!/usr/bin/env python3
# -*- coding: utf-8 -*-

print(
    "Loading updated email_claude_api module with API logging - v"
    + str(hex(id(object)))
)

import os
import sys
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
import logging
from datetime import datetime, timedelta

import anthropic
from gmail_chatbot.email_config import (
    CLAUDE_API_KEY_ENV,
    CLAUDE_DEFAULT_MODEL,
    CLAUDE_MAX_TOKENS,
    CLAUDE_PREP_MODEL,
    CLAUDE_TRIAGE_MODEL,
    DEFAULT_SYSTEM_MESSAGE,
)
from gmail_chatbot.api_logging import log_claude_request, log_claude_response
from .prompt_templates import (
    format_executable_logic_prompt,
    VECTOR_RESULTS_EVALUATION_PROMPT,
)

print(f"Claude API model in use: {CLAUDE_DEFAULT_MODEL}")

# Configure logging
import io

# Configure stdout/stderr for UTF-8 to properly handle emojis in console output
if not os.environ.get("PYTEST_RUNNING"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

logger = logging.getLogger(__name__)


class ClaudeAPIClient:
    """Client for interacting with Claude API to process email queries and responses."""

    def __init__(
        self,
        model: Optional[str] = None,
        prep_model: Optional[str] = None,
        triage_model: Optional[str] = None,
    ) -> None:
        """Initialize the Claude API client.

        Args:
            model: The Claude model to use (default from config)
            prep_model: Model used for prompt preparation (default from config)
            triage_model: Model used for inexpensive triage summaries
        """
        try:
            # Get the project root directory for better error messages
            # Determine project root for locating the .env file
            project_root = Path(__file__).resolve().parents[1]
            env_path = project_root / ".env"

            self.api_key = os.environ.get(CLAUDE_API_KEY_ENV)
            if not self.api_key:
                logging.warning(
                    f"Missing {CLAUDE_API_KEY_ENV} environment variable"
                )
                print(
                    f"[WARNING] Missing {CLAUDE_API_KEY_ENV} in environment. Claude API functionality will be limited."
                )
                print(f"Please check your .env file at {env_path}")
                # Set dummy value to avoid immediate crash, but client will fail on API calls
                self.api_key = "MISSING_API_KEY"
                self.model = model or CLAUDE_DEFAULT_MODEL
                self.prep_model = prep_model or CLAUDE_PREP_MODEL
                self.triage_model = triage_model or CLAUDE_TRIAGE_MODEL
                self.client = None  # Will be caught in API methods
            else:
                self.model = model or CLAUDE_DEFAULT_MODEL
                self.prep_model = prep_model or CLAUDE_PREP_MODEL
                self.triage_model = triage_model or CLAUDE_TRIAGE_MODEL
                self.client = anthropic.Anthropic(api_key=self.api_key)
                logging.info(
                    f"Initialized Claude API client with model {self.model}"
                )
        except Exception as e:
            logging.error(f"Error initializing Claude API client: {str(e)}")
            print(f"[ERROR] Failed to initialize Claude API client: {str(e)}")
            # Set up minimal values to avoid crashes in other parts of the code
            self.api_key = None
            self.model = model or CLAUDE_DEFAULT_MODEL
            self.prep_model = prep_model or CLAUDE_PREP_MODEL
            self.triage_model = triage_model or CLAUDE_TRIAGE_MODEL
            self.client = None

    def process_query(
        self,
        user_query: str,
        system_message: str,
        request_id: str = None,
        model: Optional[str] = None,
    ) -> str:
        """Process a user query through Claude to format it for Gmail API.

        Args:
            user_query: User's natural language query about emails
            system_message: System message to guide Claude's response
            request_id: Optional request ID for logging and tracking
            model: Model override for this request

        Returns:
            Structured query for Gmail API or ASK_USER for clarification
        """
        try:
            model_to_use = model or self.model

            # Check if client is available (could be None if API key is missing)
            if self.client is None:
                error_msg = "Claude API client not available - missing API key"
                logging.error(
                    f"[{request_id if request_id else 'NO_ID'}] {error_msg}"
                )
                return f"ERROR: {error_msg}. Please check your .env file for the {CLAUDE_API_KEY_ENV} environment variable."

            # Generate a unique request ID if not provided
            if not request_id:
                request_id = f"req_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hash(user_query) % 10000}"
            logging.info(
                f"[{request_id}] Processing user query: {user_query[:50]}..."
            )

            # Get current date for accurate time references
            current_date = datetime.now()
            current_date_str = current_date.strftime("%Y/%m/%d")
            one_week_ago = (current_date - timedelta(days=7)).strftime(
                "%Y/%m/%d"
            )
            one_month_ago = (current_date - timedelta(days=30)).strftime(
                "%Y/%m/%d"
            )

            # Use the executable logic prompt template with current date references
            context = {
                "current_date": current_date_str,
                "one_week_ago": one_week_ago,
                "one_month_ago": one_month_ago,
                "first_day_of_month": current_date.replace(day=1).strftime(
                    "%Y/%m/%d"
                ),
            }

            # Create structured prompt to convert natural language to Gmail query
            prompt = (
                f"User query: {user_query}\n\n"
                + format_executable_logic_prompt(context)
            )

            try:
                # Log the request to Claude
                request_log_path = log_claude_request(
                    model=self.model,
                    system_message=system_message,
                    user_message=prompt,
                    original_query=user_query,
                    request_id=request_id,  # Include request_id for tracking
                )
            except Exception as log_error:
                logging.warning(
                    f"[{request_id}] Failed to log Claude request, continuing: {str(log_error)}"
                )
                request_log_path = None  # We'll continue without logging

            # Log detailed diagnostic information
            logging.info(
                f"[{request_id}] Sending query to Claude API with prompt length: {len(prompt)}"
            )
            logging.info(
                f"[{request_id}] About to call Claude API. self.client is: {self.client}"
            )  # <-- ADDED LOG LINE

            # Call Claude API
            try:
                response = self.client.messages.create(
                    model=model_to_use,
                    max_tokens=CLAUDE_MAX_TOKENS,
                    system=system_message,
                    messages=[{"role": "user", "content": prompt}],
                )
            except getattr(
                anthropic, "errors", anthropic
            ).NotFoundError as api_err:
                logging.error(
                    f"[{request_id}] Claude API model not found: {api_err}"
                )
                return "ERROR: The specified Claude model is invalid or inaccessible."
            except getattr(anthropic, "APIError", Exception) as api_err:
                logging.error(f"[{request_id}] Claude API error: {api_err}")
                return "ERROR: The specified Claude model is invalid or inaccessible."

            # Extract the formatted query
            formatted_query = response.content[0].text.strip()
            logging.info(
                f"[{request_id}] Claude API returned: {formatted_query}"
            )

            # Validate the response - check if it's an error message or valid query
            if formatted_query.startswith("ASK_USER:"):
                # This is a request for clarification, return it directly
                logging.info(
                    f"[{request_id}] Claude requests clarification: {formatted_query}"
                )
                return formatted_query

            # Check for error responses
            is_error_response = any(
                error_phrase in formatted_query.lower()
                for error_phrase in [
                    "i don't",
                    "cannot",
                    "i cannot",
                    "i am unable",
                    "i'm unable",
                    "i apologize",
                    "sorry",
                    "error:",
                    "i'm an ai",
                    "as an ai",
                ]
            )

            if is_error_response:
                logging.error(
                    f"[{request_id}] Claude returned error response instead of query: {formatted_query[:100]}"
                )
                # Log critical diagnostic info
                logging.critical(
                    f"ERROR RESPONSE DETECTED - Query: '{user_query}' produced error: '{formatted_query[:100]}'"
                )
            else:
                logging.info(
                    f"[{request_id}] Formatted Gmail query: {formatted_query}"
                )

            # Log the response from Claude
            token_usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "request_id": request_id,  # Include request_id
                "is_error": is_error_response,  # Include error flag
            }
            log_claude_response(
                request_log_path=request_log_path,
                response_content=formatted_query,
                tokens_used=token_usage,
            )

            # Return the formatted query, but flag errors clearly
            if is_error_response:
                return f"ERROR: {formatted_query}"
            return formatted_query

        except Exception as e:
            error_msg = f"Error processing query with Claude API: {e}"
            logging.error(error_msg)
            logging.critical(
                f"EXCEPTION in Claude API: {str(e)} - Query: '{user_query}'"
            )
            return f"ERROR: {str(e)}"

    def process_email_content(
        self,
        email_data: Union[Dict[str, Any], List[Dict[str, Any]]],
        user_query: str,
        system_message: str,
        model: Optional[str] = None,
    ) -> str:
        """Process email content through Claude to extract or summarize information.

        Args:
            email_data: Email data from Gmail API (single email or list)
            user_query: Original user query about emails
            system_message: System message to guide Claude's response
            model: Model override for this request

        Returns:
            Processed email information
        """
        try:
            model_to_use = model or self.model

            logging.info("Processing email content through Claude")

            # Anti-hallucination check: First verify email_data is not empty
            if isinstance(email_data, list) and len(email_data) == 0:
                logging.warning(
                    "Empty email data list received - returning no results message"
                )
                return "No emails were found matching your query. Please try a different search term or time period."

            # Check for "no emails found" message in email_data (sometimes passed as a string)
            if (
                isinstance(email_data, str)
                and "no emails found" in email_data.lower()
            ):
                logging.warning(
                    "'No emails found' message received - returning no results message"
                )
                return "No emails were found matching your query. Please try a different search term or time period."

            # Validate email_data structure before processing
            if isinstance(email_data, list):
                if not all(
                    isinstance(email, dict) and "id" in email
                    for email in email_data
                ):
                    logging.error(
                        f"Invalid email data structure: {email_data}"
                    )
                    return "I encountered an error processing your search results. The email data format is invalid."
            elif isinstance(email_data, dict):
                if "id" not in email_data:
                    logging.error(
                        f"Invalid single email data structure: {email_data}"
                    )
                    return "I encountered an error processing your search results. The email data format is invalid."

            # Convert email data to JSON string for Claude
            email_json = json.dumps(email_data, indent=2)

            # Create a message to Claude asking to process the email content
            prompt = (
                "I need help analyzing the following email data based on the user's request.\n\n"
                f"User request: {user_query}\n\n"
                f"Email data: {email_json}\n\n"
                "Please analyze the email data and respond to the user's request. "
                "Format your response in a clear, concise manner. "
                "Include only relevant information and protect user privacy. "
                "IMPORTANT: NEVER make up or hallucinate email content that is not in the data."
            )

            # Log the request to Claude
            request_log_path = log_claude_request(
                model=self.model,
                system_message=system_message,
                user_message=prompt,
                original_query=user_query,
            )

            # Call Claude API
            try:
                response = self.client.messages.create(
                    model=model_to_use,
                    max_tokens=CLAUDE_MAX_TOKENS,
                    system=system_message,
                    messages=[{"role": "user", "content": prompt}],
                )
            except getattr(
                anthropic, "errors", anthropic
            ).NotFoundError as api_err:
                logging.error(f"Claude API model not found: {api_err}")
                return "Error: The specified Claude model is invalid or inaccessible."
            except getattr(anthropic, "APIError", Exception) as api_err:
                logging.error(f"Claude API error: {api_err}")
                return "Error: The specified Claude model is invalid or inaccessible."

            # Extract the processed content
            processed_content = response.content[0].text.strip()

            # Log the response from Claude
            token_usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
            log_claude_response(
                request_log_path=request_log_path,
                response_content=(
                    processed_content[:500] + "..."
                    if len(processed_content) > 500
                    else processed_content
                ),
                tokens_used=token_usage,
            )

            return processed_content

        except Exception as e:
            logging.error(
                f"Error processing email content with Claude API: {e}"
            )
            return f"Error processing email content: {str(e)}"

    def evaluate_vector_match(
        self,
        user_query: str,
        vector_results: List[Dict[str, Any]],
        system_message: str,
        request_id: str = None,
        model: Optional[str] = None,
    ) -> str:
        """Evaluate whether vector search results match user query intent and provide a relevant response.

        Args:
            user_query: Original user's natural language query
            vector_results: List of email result dictionaries from vector search
            system_message: System message to guide Claude's response
            request_id: Optional request ID for logging and tracking
            model: Model override for this request

        Returns:
            Relevance-evaluated response addressing the user's query using vector results
        """
        try:
            model_to_use = model or self.model

            # Generate a unique request ID if not provided
            if not request_id:
                request_id = f"veceval_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hash(user_query) % 10000}"

            logging.info(
                f"[{request_id}] Evaluating vector results for query: {user_query[:50]}..."
            )

            # Format the vector results into a readable summary
            vector_summary = ""
            for i, result in enumerate(
                vector_results[:5]
            ):  # Limit to top 5 results
                # Extract key email information
                subject = result.get("subject", "No subject")
                sender = result.get("from", "Unknown sender")
                date = result.get("date", "Unknown date")
                summary = result.get(
                    "summary", result.get("snippet", "No content")
                )

                # Format into a concise result entry
                vector_summary += f"{i+1}. Subject: {subject}\n   From: {sender}\n   Date: {date}\n   Summary: {summary[:150]}...\n\n"

            # Create prompt combining the user query and vector results
            prompt = f"""{VECTOR_RESULTS_EVALUATION_PROMPT}

The user asked: "{user_query}"

Here are the top results from a semantic search of their inbox:
{vector_summary}

Do these results seem relevant to the query? If yes, summarize key info. If no, suggest alternatives."""

            # Log the request to Claude
            request_log_path = log_claude_request(
                model=self.model,
                system_message=system_message,
                user_message=prompt,
                original_query=user_query,
                request_id=request_id,
            )

            # Call Claude API
            response = self.client.messages.create(
                model=model_to_use,
                max_tokens=CLAUDE_MAX_TOKENS,
                system=system_message,
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract and process the response
            evaluated_response = response.content[0].text.strip()

            # Log the response
            token_usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
            log_claude_response(
                request_log_path=request_log_path,
                response_content=(
                    evaluated_response[:500] + "..."
                    if len(evaluated_response) > 500
                    else evaluated_response
                ),
                tokens_used=token_usage,
            )

            # Clean up the response using the postprocessor
            from gmail_chatbot.query_classifier import (
                postprocess_claude_response,
            )

            cleaned_response = postprocess_claude_response(evaluated_response)

            logging.info(f"[{request_id}] Vector results evaluation complete")
            return cleaned_response

        except Exception as e:
            logging.error(
                f"[{request_id}] Error evaluating vector results: {str(e)}"
            )
            return f"I ran into an issue evaluating the search results for your query. Error: {str(e)}"

    def chat(
        self,
        message: str,
        chat_history: List[Dict[str, str]],
        system_message: str,
        model: Optional[str] = None,
    ) -> str:
        """Process a general chat message with Claude.

        Args:
            message: User's message
            chat_history: Previous chat messages
            system_message: System message to guide Claude's response
            model: Model override for this request

        Returns:
            Claude's response
        """
        try:
            model_to_use = model or self.model

            # Prepare chat history for API call
            messages = []
            for msg in chat_history:
                # Only add messages with valid role and content
                if msg.get("role") and msg.get("content"):
                    messages.append(
                        {"role": msg["role"], "content": msg["content"]}
                    )

            # Add current user message
            messages.append({"role": "user", "content": message})

            # Generate a unique request ID
            request_id = f"chat_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hash(message) % 10000}"

            # Log the request
            request_log_path = log_claude_request(
                model=self.model,
                system_message=system_message,
                user_message=message,
                original_query=message,  # Use message as the original query
                request_id=request_id,
            )

            # Call Claude API
            response = self.client.messages.create(
                model=model_to_use,
                max_tokens=CLAUDE_MAX_TOKENS,
                system=system_message,
                messages=messages,
            )

            # Extract the response content
            response_content = response.content[0].text.strip()

            # Log the response from Claude
            token_usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
            log_claude_response(
                request_log_path=request_log_path,
                response_content=(
                    response_content[:500] + "..."
                    if len(response_content) > 500
                    else response_content
                ),
                tokens_used=token_usage,
            )

            return response_content

        except Exception as e:
            logging.error(f"Error chatting with Claude API: {e}")
            return f"Error processing your message: {str(e)}"

    def summarize_triage(
        self,
        action_items: List[Dict[str, Any]],
        urgent: List[Dict[str, Any]],
        request_id: str,
    ) -> str:
        """Summarize triage information using a lightweight model."""
        try:
            if self.client is None:
                error_msg = "Claude API client not available - missing API key"
                logging.error(f"[{request_id}] {error_msg}")
                return f"ERROR: {error_msg}"

            prompt_parts = [
                "Provide a concise triage summary for the following items." \
                " Prioritize any urgent emails."
            ]
            if action_items:
                prompt_parts.append("\nAction items:")
                for item in action_items[:10]:
                    subj = item.get("subject", "No Subject")
                    date = item.get("date", "N/A")
                    prompt_parts.append(f"- {subj} (Date: {date})")
            if urgent:
                prompt_parts.append("\nUrgent emails:")
                for item in urgent[:10]:
                    subj = item.get("subject", "No Subject")
                    date = item.get("date", "N/A")
                    prompt_parts.append(f"- {subj} (Date: {date})")
            prompt_parts.append(
                "\nSummarize these items and suggest next steps in a few sentences."
            )
            prompt = "\n".join(prompt_parts)

            request_log_path = log_claude_request(
                model=self.triage_model,
                system_message=DEFAULT_SYSTEM_MESSAGE,
                user_message=prompt,
                original_query="triage",
                request_id=request_id,
            )

            response = self.client.messages.create(
                model=self.triage_model,
                max_tokens=CLAUDE_MAX_TOKENS,
                system=DEFAULT_SYSTEM_MESSAGE,
                messages=[{"role": "user", "content": prompt}],
            )

            summary = response.content[0].text.strip()

            token_usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
            log_claude_response(
                request_log_path=request_log_path,
                response_content=summary,
                tokens_used=token_usage,
            )

            return summary

        except getattr(anthropic, "errors", anthropic).NotFoundError as api_err:
            logging.error(f"[{request_id}] Claude API model not found: {api_err}")
            return "ERROR: The specified Claude model is invalid or inaccessible."
        except getattr(anthropic, "APIError", Exception) as api_err:
            logging.error(f"[{request_id}] Claude API error: {api_err}")
            return "ERROR: The specified Claude model is invalid or inaccessible."
        except Exception as e:
            logging.error(f"[{request_id}] Error summarizing triage: {e}")
            return f"Error summarizing triage: {str(e)}"
