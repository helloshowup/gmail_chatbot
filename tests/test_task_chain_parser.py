import sys
from pathlib import Path

# Ensure project root is on the path
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from gmail_chatbot.task_chain_parser import parse_task_chain


def test_parse_task_chain_bullet_lines_ignored():
    """Bullet lines should not produce separate steps."""
    text = (
        "TASK_CHAIN:\n"
        "1. Search inbox for budget updates\n"
        "\u2022 New clients or projects\n"
        "2. Summarize the results\n"
        "Would you like me to proceed?"
    )
    plan = parse_task_chain(text)
    assert len(plan) == 2
    assert [step["action_type"] for step in plan] == [
        "search_inbox",
        "summarize_text",
    ]

