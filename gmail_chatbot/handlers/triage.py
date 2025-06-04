"""Triage-related query handling for Gmail Chatbot."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, TYPE_CHECKING

from gmail_chatbot.query_classifier import postprocess_claude_response

if TYPE_CHECKING:
    from gmail_chatbot.app.core import GmailChatbotApp


def _recent_triage_provided(app: "GmailChatbotApp", look_back: int = 3) -> bool:
    """Check recent assistant messages for triage content."""
    keywords = [
        "need your attention",
        "quick search",
        "immediate attention",
    ]
    count = 0
    for entry in reversed(app.chat_history):
        if entry.get("role") != "assistant":
            continue
        if any(k in entry.get("content", "").lower() for k in keywords):
            return True
        count += 1
        if count >= look_back:
            break
    return False


def handle_triage_query(
    app: "GmailChatbotApp",
    message: str,
    request_id: str,
    scores: Dict[str, float],
) -> str:
    """Handle queries classified as ``triage`` or triage-leaning ``ambiguous``.

    Parameters
    ----------
    app:
        The application instance used to access memory and Claude client.
    message:
        The original user message.
    request_id:
        Unique identifier for logging.
    scores:
        Classification confidence scores.

    Returns
    -------
    str
        Assistant response summarizing urgent items or related emails.
    """
    logging.info(
        f"[{request_id}] Handling 'triage' or triage-leaning 'ambiguous' query (scores: {scores})."
    )
    response = ""
    action_items = app.memory_actions_handler.get_action_items_structured(
        request_id=request_id
    )

    if action_items:
        grouped = defaultdict(list)
        for item in action_items:
            grouped[item.get("client", "Other Tasks")].append(item)

        response_parts = ["Here are items that might need your attention:\n"]
        for client_name, items in grouped.items():
            response_parts.append(f"**{client_name}** ({len(items)} item(s))")
            for item in items[:4]:
                response_parts.append(
                    f"- {item.get('subject', 'No Subject')} (Date: {item.get('date', 'N/A')})"
                )
            if len(items) > 4:
                response_parts.append(f"  ...and {len(items) - 4} more.")
            response_parts.append("")

        delegation_candidates = app.memory_actions_handler.get_delegation_candidates(
            action_items, request_id=request_id
        )
        if delegation_candidates:
            response_parts.append("\n**Potential tasks for your VA:**")
            for item in delegation_candidates[:3]:
                response_parts.append(f"- {item.get('subject', 'No Subject')}")
        response = "\n".join(response_parts)
    elif (
        app.memory_actions_handler.is_vector_search_available(request_id=request_id)
        and not _recent_triage_provided(app)
    ):
        logging.info(
            f"[{request_id}] No action items for triage, trying vector search for relevant emails."
        )
        vector_results = app.memory_actions_handler.find_related_emails(
            message, limit=5, request_id=request_id
        )
        if vector_results:
            response = app.claude_client.evaluate_vector_match(
                user_query=message,
                vector_results=vector_results,
                system_message=app.system_message,
                request_id=request_id,
            )
            response = postprocess_claude_response(response)
        else:
            response = (
                "I checked for urgent items and also performed a quick search based "
                "on your message, but didn't find anything specific that needs immediate attention."
            )
    elif _recent_triage_provided(app):
        response = (
            "I've recently provided a triage summary. Let me know if you need more details."
        )
    else:
        response = (
            "I checked for urgent items, but there's nothing specific in the action list right now, "
            "and semantic search is unavailable to find related emails."
        )
    return response

