"""Triage-related query handling for Gmail Chatbot.

This module summarizes urgent emails and action items using Claude when
possible.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List, TYPE_CHECKING, Any

from gmail_chatbot.query_classifier import postprocess_claude_response

if TYPE_CHECKING:
    from gmail_chatbot.app.core import GmailChatbotApp


def handle_triage_query(
    app: "GmailChatbotApp",
    message: str,
    request_id: str,
    scores: Dict[str, float],
) -> str:
    """Handle queries classified as ``triage`` or triage-leaning ``ambiguous``.

    When action items or urgent emails are detected, the results are summarized
    using Claude before falling back to manual formatting if needed.

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
    urgent_results: List[Dict[str, Any]] = []
    if app.memory_actions_handler.is_vector_search_available(
        request_id=request_id
    ):
        urgent_query = "urgent OR ASAP"
        urgent_results = app.memory_actions_handler.find_related_emails(
            urgent_query, limit=5, request_id=f"{request_id}_urgent"
        )
        for item in urgent_results:
            text = (
                f"{item.get('subject', '')} {item.get('summary', '')}".lower()
            )
            score = 0
            if "urgent" in text:
                score += 2
            if "asap" in text or "as soon as possible" in text:
                score += 1
            item["_urgency"] = score
        urgent_results.sort(
            key=lambda x: (x.get("_urgency", 0), x.get("date", "")),
            reverse=True,
        )

    if action_items or urgent_results:
        summary = ""
        try:
            summary = app.claude_client.summarize_triage(
                action_items,
                urgent_results,
                request_id=request_id,
            )
        except Exception as e:  # pragma: no cover - log and fall back
            logging.error(f"[{request_id}] Claude triage summary failed: {e}")

        if summary and not summary.lower().startswith("error"):
            return summary

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

        if urgent_results:
            grouped_urgent = defaultdict(list)
            for item in urgent_results:
                grouped_urgent[item.get("client", "Other Emails")].append(item)

            response_parts.append("**Urgent Emails Detected:**")
            for client_name, items in grouped_urgent.items():
                response_parts.append(
                    f"**{client_name}** ({len(items)} item(s))"
                )
                for item in items[:4]:
                    bullet = f"- {item.get('subject', 'No Subject')} (Date: {item.get('date', 'N/A')}) [URGENT]"
                    response_parts.append(bullet)
                if len(items) > 4:
                    response_parts.append(f"  ...and {len(items) - 4} more.")
                response_parts.append("")

        delegation_candidates = (
            app.memory_actions_handler.get_delegation_candidates(
                action_items, request_id=request_id
            )
        )
        if delegation_candidates:
            response_parts.append("\n**Potential tasks for your VA:**")
            for item in delegation_candidates[:3]:
                response_parts.append(f"- {item.get('subject', 'No Subject')}")
        response = "\n".join(response_parts)
    elif app.memory_actions_handler.is_vector_search_available(
        request_id=request_id
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
            search_prompt = "Should I check your inbox"
            recent_info = app.has_recent_assistant_phrase(
                "items that might need your attention"
            ) or app.has_recent_assistant_phrase(search_prompt)
            if recent_info:
                response = "I already looked for urgent items recently and didn't find anything new."
            else:
                response = (
                    "I checked for urgent items and also performed a quick search based "
                    "on your message, but didn't find anything specific that needs immediate attention. "
                    "Should I check your inbox directly for more recent updates?"
                )
    else:
        response = (
            "I checked for urgent items, but there's nothing specific in the action list right now, "
            "and semantic search is unavailable to find related emails."
        )
    return response
