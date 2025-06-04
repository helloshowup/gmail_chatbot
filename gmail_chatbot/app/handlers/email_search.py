"""Email search query handler for Gmail Chatbot."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gmail_chatbot.app.core import GmailChatbotApp


def handle_email_search_query(
    app: "GmailChatbotApp",
    message: str,
    message_lower: str,
    request_id: str,
) -> str:
    """Handle queries classified as ``email_search``.

    Parameters
    ----------
    app:
        Application instance for accessing state and services.
    message:
        Original user message.
    message_lower:
        Lowercased version of the message for checking patterns.
    request_id:
        Unique identifier for logging.

    Returns
    -------
    str
        Response to send back to the user.
    """
    logging.info(
        f"[{request_id}] Handling 'email_search' query: {message[:50]}..."
    )
    response = ""

    if app._is_simple_inbox_query(message_lower):
        logging.info(
            f"[{request_id}] Query '{message[:50]}' identified as simple inbox query. Offering menu."
        )

        today_str = date.today().strftime("%Y/%m/%d")
        yesterday = date.today() - timedelta(days=1)
        yesterday_str = yesterday.strftime("%Y/%m/%d")

        menu_options_map = {
            "1": {
                "type": "search_emails",
                "query": "is:unread",
                "description": "Recent unread emails",
            },
            "2": {
                "type": "search_emails",
                "query": f"is:unread after:{yesterday_str}",
                "description": "Unread since yesterday",
            },
            "3": {
                "type": "search_emails",
                "query": f"is:important after:{today_str}",
                "description": "Important today",
            },
            "4": {
                "type": "search_emails",
                "query": "is:starred",
                "description": "Starred emails",
            },
        }

        response_parts = [
            "Okay, I can check your emails. What specifically are you interested in?"
        ]
        for key_num, val_details in menu_options_map.items():
            response_parts.append(
                f"{key_num}. {val_details['description']}"
            )
        response_parts.append(
            "\nPlease enter the number of your choice, or ask something else."
        )
        response = "\n".join(response_parts)

        app.pending_email_context = {
            "type": "email_menu",
            "options": menu_options_map,
            "original_message": message,
        }
        logging.info(
            f"[{request_id}] Set pending_email_context for email menu. Options: {{k: v['description'] for k, v in menu_options_map.items()}}"
        )
    else:
        logging.info(
            f"[{request_id}] Query '{message[:50]}' is complex email_search. Using standard Claude-assisted search flow."
        )
        query_suggestion_from_claude = app.claude_client.process_query(
            user_query=message,
            system_message=app.system_message,
            request_id=request_id,
            model=app.claude_client.prep_model,
        )

        if query_suggestion_from_claude.startswith("ASK_USER:"):
            response = query_suggestion_from_claude.replace(
                "ASK_USER:", ""
            ).strip()
            app.pending_email_context = (
                None
            )
            logging.info(
                f"[{request_id}] Claude needs clarification for email search: {response}"
            )
        elif query_suggestion_from_claude.startswith("ERROR:"):
            response = (
                "I encountered an issue trying to understand your email search: "
                f"{query_suggestion_from_claude.replace('ERROR:', '').strip()}"
            )
            app.pending_email_context = None
            logging.error(
                f"[{request_id}] Claude returned an error for email search: {query_suggestion_from_claude}"
            )
        else:
            app.pending_email_context = {
                "gmail_query": query_suggestion_from_claude,
                "original_message": message,
                "type": "gmail_query_confirmation",
            }
            response = (
                "Okay, I can search for that. To confirm, do you want me to search Gmail for: "
                f"`{query_suggestion_from_claude}`? (yes/no)"
            )
            logging.info(
                f"[{request_id}] Email search needs confirmation for query: '{query_suggestion_from_claude}'. Set pending_email_context."
            )
    return response
