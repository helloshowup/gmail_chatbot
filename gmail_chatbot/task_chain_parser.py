"""Parse Claude-generated TASK_CHAIN instructions into executable plan steps."""

from __future__ import annotations

import re
from typing import Any, Dict, List


STEP_SPLIT_PATTERN = re.compile(r"(?:^|\n)\s*(?:step\s*\d+[:\.)]|\d+\)|-\s+|\u2022)\s*", re.IGNORECASE)


def _infer_action_type(description: str) -> str:
    """Infer the action type for a step based on keywords."""
    desc = description.lower()
    if "search" in desc or "look" in desc:
        return "search_inbox"
    if "extract" in desc or "analyz" in desc:
        return "extract_entities"
    if "summarize" in desc or "summary" in desc:
        return "summarize_text"
    if "notebook" in desc or "log" in desc:
        return "log_to_notebook"
    if "send" in desc and "email" in desc:
        return "send_email"
    return "placeholder_action"


def parse_task_chain(text: str) -> List[Dict[str, Any]]:
    """Convert TASK_CHAIN text into a list of plan step dictionaries.

    Segments that do not map to a recognized action type are ignored.
    """
    if "TASK_CHAIN:" in text:
        text = text.split("TASK_CHAIN:", 1)[1]

    # Remove trailing confirmation questions
    end_match = re.search(r"(would you|shall i|should i|can i|do you)", text, re.IGNORECASE)
    if end_match:
        text = text[: end_match.start()]

    segments = STEP_SPLIT_PATTERN.split(text)
    steps: List[Dict[str, Any]] = []
    index = 1
    for seg in segments:
        desc = seg.strip().strip("- ")
        if not desc:
            continue
        action_type = _infer_action_type(desc)
        if action_type == "placeholder_action":
            # treat bullet-list details as notes, not steps
            continue
        steps.append(
            {
                "step_id": f"step_{index}",
                "description": desc,
                "action_type": action_type,
                "parameters": {},
                "output_key": f"step_{index}_output",
            }
        )
        index += 1
    return steps

