#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, TYPE_CHECKING
import queue
import threading

from .prompt_templates import NOTEBOOK_EMPTY_PROMPT, NOTEBOOK_SUMMARY_PREFIX
from gmail_chatbot.preference_detector import PreferenceDetector


if TYPE_CHECKING:
    from gmail_chatbot.email_memory_vector import EmailVectorMemoryStore # Corrected import path
    from gmail_chatbot.email_gmail_api import GmailAPIClient
    from gmail_chatbot.email_claude_api import ClaudeAPIClient
    from gmail_chatbot.preference_detector import PreferenceDetector

logger = logging.getLogger(__name__)

class MemoryActionsHandler:
    """Handles higher-level actions related to memory, knowledge base, and autonomous tasks."""

    def __init__(
        self,
        memory_store: 'EmailVectorMemoryStore',
        gmail_client: 'GmailAPIClient',
        claude_client: 'ClaudeAPIClient',
        system_message: str,
        preference_detector: 'PreferenceDetector', # Added
    ) -> None:
        """Initialize the MemoryActionsHandler.

        Args:
            memory_store: Instance of EmailVectorMemoryStore.
            gmail_client: Instance of GmailAPIClient.
            claude_client: Instance of ClaudeAPIClient.
            system_message: The default system message for Claude.
            preference_detector: Instance of PreferenceDetector. # Added
        """
        self.memory_store = memory_store
        self.gmail_client = gmail_client
        self.claude_client = claude_client
        self.system_message = system_message
        self.preference_detector = preference_detector
        self._proactive_summary_queue = queue.Queue() # Thread-safe queue for summaries
        self._summary_lock = threading.Lock() # Lock for summary generation if needed, though Queue is thread-safe
        logger.info("MemoryActionsHandler initialized with PreferenceDetector and proactive summary queue")

    def get_handler_client_names(self) -> List[str]:
        """Retrieve all client names from the memory store."""
        return self.memory_store.get_client_names()

    def add_handler_client_info(self, client_name: str, client_data: Dict[str, Any]) -> None:
        """Add client information to the memory store.

        Args:
            client_name: The name of the client.
            client_data: A dictionary containing client information.
        """
        self.memory_store.add_client_info(client_name, client_data)
        logger.info(f"Client '{client_name}' info added/updated via MemoryActionsHandler.")

    def store_emails_in_memory(
        self, emails: List[Dict[str, Any]], query: str, request_id: str
    ) -> None:
        """Store emails in the memory store.

        Args:
            emails: List of email data dictionaries
            query: The query that produced these emails
            request_id: Unique ID for tracking this request in logs
        """
        if not emails:
            logger.info(f"[{request_id}] No emails to store for query: {query}")
            return

        logger.info(f"[{request_id}] Storing {len(emails)} emails for query: {query}")
        for email_data in emails:
            try:
                self.memory_store.add_email_memory(
                    email_id=email_data.get("id", "unknown_id"),
                    subject=email_data.get("subject", "No Subject"),
                    sender=email_data.get("sender", "Unknown Sender"),
                    recipient=email_data.get("recipient", "Unknown Recipient"),
                    date=email_data.get("date", datetime.now().isoformat()),
                    summary=email_data.get("summary", "No Summary"),
                    body=email_data.get("body"), # Pass body for vector indexing
                    client=email_data.get("client"), # If client is determined earlier
                    tags=email_data.get("tags", []) + [f"query:{query}"],
                    requires_action=email_data.get("requires_action", False),
                    action_type=email_data.get("action_type")
                )
            except Exception as e:
                logger.error(f"[{request_id}] Error storing email {email_data.get('id')}: {e}")
        logger.info(f"[{request_id}] Finished storing emails.")

    def handle_user_memory_query(self, message: str, request_id: str) -> Optional[str]:
        """Handle queries about stored memory information by dispatching to specific handlers.

        Args:
            message: User query.
            request_id: Unique ID for tracking this request in logs.

        Returns:
            Response based on memory, or None if not applicable.
        """
        query_lower = message.lower()
        response = None
        logger.info(f"[{request_id}] Attempting to handle user memory query: {message[:50]}...")

        # Handle notebook overview/status queries first
        notebook_overview_triggers = [
            "notebook status", "memory status", "what's in my notebook",
            "notebook summary", "show notebook", "tell me about my notebook",
            # Retaining some of the old db_status_triggers if they imply a general overview
            "status", "memory size", "database stats", "vector status", "db status"
        ]
        if any(term in query_lower for term in notebook_overview_triggers):
            logger.info(f"[{request_id}] Identified as notebook overview query.")
            response = self.get_notebook_overview(request_id)
            if response: return response

        # Check for preference queries
        preference_triggers = [
            "preference", "preferences", "what i like", "what i dislike",
            "what i hate", "what i love", "my settings",
        ]
        if any(term in query_lower for term in preference_triggers):
            logger.info(f"[{request_id}] Identified as preference query.")
            response = self.manage_preferences(message, request_id)
            if response: return response

        # Display detailed/technical vector DB status if specifically requested (e.g., for debugging)
        # This is now separate from the general 'notebook status' which is handled above.
        technical_db_status_triggers = [
            "technical db status", "vector details", "show vector stats"
        ]
        if any(term in query_lower for term in technical_db_status_triggers):
            logger.info(f"[{request_id}] Identified as technical DB status query.")
            response = self.get_db_status() # self.get_db_status() still exists for this more technical view
            if response: return response

        # Check for client-specific queries
        client_names = self.memory_store.get_client_names()
        for client_name in client_names:
            if client_name.lower() in query_lower:
                logger.info(f"[{request_id}] Identified as client query for: {client_name}")
                client_response = self.get_client_info(client_name)
                if client_response:
                    return client_response
        
        # Check for action item queries
        action_item_triggers = [
            "action", "todo", "to do", "task", "pending",
            "attention", "follow up", "followup", "urgent", "what have i missed", "what needs attention"
        ]
        if any(term in query_lower for term in action_item_triggers):
            logger.info(f"[{request_id}] Identified as action items query.")
            response = self.get_action_items()
            if response: return response

        # Check for delegation suggestions
        delegation_triggers = [
            "delegate", "virtual assistant", "va", "assistant",
            "hand off", "handoff", "pass along", "what can be delegated",
        ]
        if any(term in query_lower for term in delegation_triggers):
            logger.info(f"[{request_id}] Identified as delegation query.")
            response = self.get_delegation_tasks()
            if response: return response

        # Check for saved note listings
        notes_triggers = ["list notes", "show notes", "my notes"]
        if any(term in query_lower for term in notes_triggers):
            logger.info(f"[{request_id}] Identified as notes listing query.")
            response = self.list_saved_notes()
            if response:
                return response

        if not response:
            logger.info(f"[{request_id}] User memory query '{message[:50]}' did not match any specific handlers in MemoryActionsHandler.")

        return response

    def get_notebook_overview(self, request_id: str) -> str:
        """Provide an overview of the notebook's contents or state if it's empty."""
        logger.info(f"[{request_id}] Generating notebook overview.")
        if self.memory_store.is_notebook_empty():
            logger.info(f"[{request_id}] Notebook is empty.")
            return NOTEBOOK_EMPTY_PROMPT
        else:
            logger.info(f"[{request_id}] Notebook has content, generating summary.")
            summary = self.memory_store.get_concise_notebook_summary()
            return f"{NOTEBOOK_SUMMARY_PREFIX}{summary}"

    def _create_and_queue_enrichment_summary(self, processed_emails_count: int, new_notes_count: int, client_name: Optional[str] = None, errors_occurred: bool = False) -> None:
        """Formats and queues a summary of the enrichment process."""
        summary_parts = ["✨ **Background Update:**"]
        if client_name:
            summary_parts.append(f"For client '{client_name}':")

        if processed_emails_count > 0:
            summary_parts.append(f"Processed {processed_emails_count} email(s).")
        if new_notes_count > 0:
            summary_parts.append(f"Created {new_notes_count} note(s).")
        
        if not processed_emails_count and not new_notes_count and not errors_occurred:
            if client_name: # Only add 'no new items' if specific client was targeted
                summary_parts.append("No new items found or actions taken.")
            # If no client_name, it implies a general scan, so silence might be better if nothing found globally.
            # However, for per-client processing, 'no new items' is informative.

        if errors_occurred:
            summary_parts.append("Some errors occurred during the process.")

        # Only queue a message if there's something meaningful to report or it's a targeted client check
        if len(summary_parts) > 1: # More than just the header
            summary_message = " ".join(summary_parts)
            try:
                self._proactive_summary_queue.put_nowait(summary_message)
                logger.info(f"Queued proactive summary: {summary_message}")
            except queue.Full:
                logger.warning("Proactive summary queue is full. Discarding summary.")
        else:
            logger.info("No significant enrichment activity to summarize proactively.")

    def get_pending_proactive_summaries(self) -> List[str]:
        """Retrieves all pending proactive summaries from the queue."""
        summaries = []
        while not self._proactive_summary_queue.empty():
            try:
                summaries.append(self._proactive_summary_queue.get_nowait())
            except queue.Empty:
                # Should not happen due to the loop condition, but good for safety
                break
        if summaries:
            logger.info(f"Retrieved {len(summaries)} proactive summaries from queue.")
        return summaries

    def perform_autonomous_memory_enrichment(self, request_id: str) -> None:
        """
        Autonomously fetches and stores recent emails for known clients.
        """
        logger.info(f"[{request_id}] Starting autonomous memory enrichment task.")
        client_names = self.memory_store.get_client_names()
        if not client_names:
            logger.info(f"[{request_id}] No clients found for autonomous memory enrichment.")
            return

        for client_name in client_names:
            try:
                logger.info(f"[{request_id}] Fetching recent emails for client: {client_name}")
                # Formulate a Gmail search query for emails related to the client in the last 7 days.
                gmail_search_query = f'"{client_name}" newer_than:7d'
                
                # search_emails returns a tuple: (list_of_email_dicts, claude_response_string)
                emails_data_list, _ = self.gmail_client.search_emails(
                    query=gmail_search_query,
                    original_user_query=f"Autonomous fetch for {client_name}", 
                    request_id=f"{request_id}_client_{client_name.replace(' ', '_')}"
                )

                if emails_data_list:
                    logger.info(f"[{request_id}] Found {len(emails_data_list)} emails for client {client_name}. Storing them.")
                    for email in emails_data_list:
                        if "client" not in email or not email["client"]:
                            email["client"] = client_name
                        if "tags" not in email or not isinstance(email["tags"], list):
                            email["tags"] = []
                        if "autonomously_fetched" not in email["tags"]:
                             email["tags"].append("autonomously_fetched")
                                
                logger.info(f"[{request_id}] Fetched {len(emails_data_list)} emails for {client_name}. Processing...")
                
                processed_email_ids = [email['id'] for email in emails_data_list]
                # Simulate storing/processing these emails. 
                # In a real scenario, this would involve calls to store_emails_in_memory or similar,
                # and potentially creating notes if logic dictates.
                # For this example, we'll assume all fetched emails are 'processed'.
                num_processed = len(emails_data_list)
                num_notes_created = 0 # Placeholder - actual note creation logic would be complex

                if num_processed > 0:
                    # This is where you would call self.store_emails_in_memory if not already done
                    # For example, if GmailAPIClient.get_recent_emails_for_client doesn't auto-summarize/store:
                    # self.store_emails_in_memory(recent_emails, query=f"autonomous_client_scan:{client_name}", request_id=request_id)
                    self.store_emails_in_memory(
                        emails=emails_data_list, 
                        query=f"Autonomously fetched for {client_name}", 
                        request_id=request_id
                    )

                # After processing for this client, create and queue a summary
                self._create_and_queue_enrichment_summary(
                    processed_emails_count=num_processed, 
                    new_notes_count=num_notes_created, 
                    client_name=client_name
                )

            except Exception as e:
                logger.error(f"[{request_id}] Error during autonomous enrichment for client {client_name}: {e}")
                self._create_and_queue_enrichment_summary(0, 0, client_name=client_name, errors_occurred=True)

        logger.info(f"[{request_id}] Autonomous memory enrichment task completed cycle.")

    def record_interaction_in_memory(
        self,
        query: str,
        response: str,
        request_id: str,
        email_ids: Optional[List[str]] = None,
        client: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        """Record a user interaction (query and response) in the memory store.

        Args:
            query: The user's query.
            response: The assistant's response.
            request_id: Unique ID for tracking this request.
            email_ids: Optional list of email IDs related to the interaction.
            client: Optional client name related to the interaction.
            tags: Optional list of tags for the interaction.
        """
        try:
            self.memory_store.record_interaction(
                query=query,
                response=response,
                email_ids=email_ids,
                client=client,
                    # request_id is not a direct param of memory_store.record_interaction
                # but useful for logging within this handler method if needed.
            )
            logger.info(f"[{request_id}] Interaction recorded: Query='{query[:50]}...', Client='{client}'")
        except Exception as e:
            logger.error(f"[{request_id}] Error recording interaction (Query='{query[:50]}...'): {e}", exc_info=True)


    def query_memory(
        self, message: str, request_id: str
    ) -> Optional[str]:
        """Handle queries about stored memory information.

        Args:
            message: User query
            request_id: Unique ID for tracking this request in logs

        Returns:
            Response based on memory, or None if not applicable
        """
        message_lower = message.lower()
        response = None

        if "database status" in message_lower or "vector status" in message_lower:
            response = self.get_db_status()
        elif "client info" in message_lower or re.search(r"tell me about client (.+)", message_lower):
            match = re.search(r"client (.+)", message_lower)
            if match:
                client_name = match.group(1).strip()
                response = self.get_client_info(client_name)
            else:
                response = "Which client are you asking about?"
        elif "action items" in message_lower or "what needs attention" in message_lower:
            response = self.get_action_items()
        elif "delegation candidates" in message_lower or "what can i delegate" in message_lower:
            response = self.get_delegation_tasks()
        # Add more specific memory query handlers here if needed

        if response:
            logger.info(f"[{request_id}] Handled memory query: '{message[:50]}' with response: '{response[:50]}...'" )
        return response

    def get_db_status(self) -> str:
        """Handle query about vector database status.

        Returns:
            Formatted status information
        """
        status = self.memory_store.get_vector_status()
        response_parts = ["Vector DB Status:"]
        for key, value in status.items():
            response_parts.append(f"- {key.replace('_', ' ').title()}: {value}")
        return "\n".join(response_parts)

    def get_client_info(self, client_name: str) -> str:
        """Handle query about a specific client.

        Args:
            client_name: The name of the client being queried

        Returns:
            Formatted client information or message if client not found
        """
        client_info = self.memory_store.get_client_context(client_name)
        if not client_info:
            return f"No information found for client: {client_name}"

        response_parts = [f"Client Information for {client_name}:"]
        for key, value in client_info.items():
            if isinstance(value, dict):
                response_parts.append(f"- {key.replace('_', ' ').title()}:")
                for sub_key, sub_value in value.items():
                    response_parts.append(f"  - {sub_key.replace('_', ' ').title()}: {sub_value}")
            else:
                response_parts.append(f"- {key.replace('_', ' ').title()}: {value}")
        return "\n".join(response_parts)

    def get_action_items(self) -> str:
        """Handle query about action items/tasks that need attention.

        Returns:
            Formatted list of action items grouped by client
        """
        action_items = self.memory_store.get_action_items()
        if not action_items:
            return "No pending action items found."

        response_parts = ["Action Items:"]
        # Group by client for better readability
        grouped_items: Dict[str, List[Dict[str, Any]]] = {}
        for item in action_items:
            client = item.get("client", "General")
            if client not in grouped_items:
                grouped_items[client] = []
            grouped_items[client].append(item)

        for client, items in grouped_items.items():
            response_parts.append(f"\nClient: {client}")
            for item in items:
                response_parts.append(
                    f"- Subject: {item.get('subject', 'N/A')}, Action: {item.get('action_type', 'N/A')}, Date: {item.get('date')}"
                )
        return "\n".join(response_parts)

    def get_action_items_structured(
        self, request_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return action items that require attention.

        Parameters
        ----------
        request_id:
            Optional identifier used for logging.

        Returns
        -------
        List[Dict[str, Any]]
            Action items as provided by the memory store.
        """
        if request_id:
            logger.info(f"[{request_id}] Retrieving structured action items.")
        else:
            logger.info("Retrieving structured action items.")
        return self.memory_store.get_action_items()

    def manage_preferences(self, message: str, request_id: str) -> str:
        """Handle queries about user preferences.

        Args:
            message: User query about preferences
            request_id: Unique ID for tracking this request in logs

        Returns:
            Formatted string response with user preference information
        """
        # This is a placeholder. Preference management logic would go here.
        # For now, it might just report stored preferences or state it's not fully implemented.
        logger.info(f"[{request_id}] Preference query: {message}")
        # Example: Fetching from memory_store if preferences are stored there
        # preferences = self.memory_store.get_user_preferences() 
        # if preferences: return f"Current preferences: {preferences}"
        return "User preference management is under development. Currently, I adapt based on our interactions."

    def _get_delegation_candidates(self, action_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract items suitable for delegation from action items.

        Args:
            action_items: List of action items to analyze

        Returns:
            List of items that are good candidates for delegation
        """
        # Simple heuristic: items that are tasks and not requiring direct personal oversight
        # This could be enhanced with Claude's help for more nuanced suggestions
        delegation_candidates = []
        for item in action_items:
            # Example criteria: if action_type is 'follow-up', 'draft_reply', 'schedule'
            if item.get("action_type") in ["follow-up", "draft_reply", "schedule_meeting"]:
                delegation_candidates.append(item)
        return delegation_candidates

    def get_delegation_tasks(self) -> str:
        """Handle query about tasks that could be delegated.

        Returns:
            Formatted list of tasks suitable for delegation
        """
        action_items = self.memory_store.get_action_items()
        if not action_items:
            return "No action items found to assess for delegation."

        delegation_candidates = self._get_delegation_candidates(action_items)
        if not delegation_candidates:
            return "No specific tasks suitable for delegation identified at the moment."

        response_parts = ["Tasks that could potentially be delegated:"]
        for item in delegation_candidates:
            response_parts.append(
                f"- Subject: {item.get('subject', 'N/A')} (Action: {item.get('action_type', 'N/A')}, Client: {item.get('client', 'General')})"
            )
        return "\n".join(response_parts)

    def list_saved_notes(self) -> str:
        """Return a list of notes stored in the memory entries."""
        notes = [
            e for e in self.memory_store.memory_entries
            if e.get("type") == "note" or e.get("kind") == "note"
        ]
        if not notes:
            return "No saved notes found."

        lines = ["Saved Notes:"]
        for idx, note in enumerate(notes, 1):
            content = note.get("content", "")
            date = note.get("date") or note.get("ts", "")
            if isinstance(date, str) and len(date) > 10:
                date = date[:10]
            lines.append(f"{idx}. {content} ({date})")
        return "\n".join(lines)

    def run_autonomous_enrichment(self, request_id: str) -> str:
        """Perform autonomous multi-step memory enrichment.

        This method autonomously enriches the memory store by searching for emails
        from the last 3 months for each known client and adding them to the vector memory.

        Args:
            request_id: Unique ID for tracking this request in logs

        Returns:
            A formatted summary of the enrichment results
        """
        logger.info(f"[{request_id}] Starting autonomous memory enrichment task.")
        results_summary = ["Autonomous Memory Enrichment Task Results:"]
        clients_to_process = self.memory_store.get_client_names()

        if not clients_to_process:
            msg = f"[{request_id}] No clients found in memory to process for enrichment."
            logger.warning(msg)
            return msg

        # Define the date range for the search (last 3 months)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)
        date_query_part = f"after:{start_date.strftime('%Y/%m/%d')} before:{end_date.strftime('%Y/%m/%d')}"

        for client_name in clients_to_process:
            logger.info(f"[{request_id}] Processing client: {client_name} for enrichment.")
            # Construct a broad query for the client
            # This could be refined, e.g., by using client-specific keywords if available
            # For now, we assume client name might appear in 'from', 'to', or 'subject'
            query = f'(from:"{client_name}" OR to:"{client_name}" OR subject:"{client_name}") {date_query_part}'
            
            try:
                # Use GmailAPIClient to search emails
                # The search_emails method might need slight adjustment if its signature differs
                # or if it expects a query processed by Claude first.
                # For autonomous tasks, direct Gmail query construction is often preferred.
                emails = self.gmail_client.search_emails(
                    query=query,
                    request_id=(
                        f"{request_id}_enrich_{client_name.replace(' ', '_')}"
                    ),
                )
                emails = emails[:25]

                if emails:
                    logger.info(f"[{request_id}] Found {len(emails)} emails for client {client_name}. Storing them.")
                    # Add client information to each email if not already present
                    for email_data in emails:
                        email_data['client'] = client_name
                        # We might need to fetch full email content (body) here if search_emails doesn't provide it
                        # and if it's needed for `store_emails_in_memory` to do vector indexing.
                        # Assuming `search_emails` can provide `body` or `store_emails_in_memory` handles its absence.
                        if 'body' not in email_data or not email_data['body']:
                            # Fetch full email if body is missing for vectorization
                            full_email_details = self.gmail_client.get_email_by_id(
                                email_data['id'], request_id=request_id
                            )
                            if full_email_details:
                                email_data['body'] = full_email_details.get('body', '')
                                email_data['summary'] = full_email_details.get(
                                    'summary', email_data.get('summary', '')
                                )  # Update summary if better one is fetched

                    self.store_emails_in_memory(emails, f"enrichment_task_for_{client_name}", request_id)
                    results_summary.append(f"- Client {client_name}: Stored {len(emails)} emails from the last 3 months.")
                else:
                    logger.info(f"[{request_id}] No new emails found for client {client_name} in the last 3 months.")
                    results_summary.append(f"- Client {client_name}: No new emails found.")
            except Exception as e:
                error_msg = f"Error processing client {client_name} for enrichment: {e}"
                logger.error(f"[{request_id}] {error_msg}")
                results_summary.append(f"- Client {client_name}: Error - {e}")
        
        final_summary = "\n".join(results_summary)
        logger.info(f"[{request_id}] Autonomous memory enrichment task completed. Summary: {final_summary}")
        return final_summary
