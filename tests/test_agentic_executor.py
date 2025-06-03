import sys
import types
import unittest
from unittest.mock import MagicMock

# Provide a minimal streamlit stub if streamlit is not available
if 'streamlit' not in sys.modules:
    st_stub = types.ModuleType('streamlit')
    st_stub.toast = lambda *args, **kwargs: None
    st_stub.session_state = types.SimpleNamespace()
    sys.modules['streamlit'] = st_stub
else:
    st_stub = sys.modules['streamlit']
    if not hasattr(st_stub, 'session_state'):
        st_stub.session_state = types.SimpleNamespace()
    if not hasattr(st_stub, 'toast'):
        st_stub.toast = lambda *args, **kwargs: None

from agentic_executor import execute_step

class TestAgenticExecutorFlow(unittest.TestCase):
    def setUp(self):
        self.gmail_client = MagicMock()
        self.gmail_client.search_emails.return_value = ([{"id": "1", "snippet": "hi"}], "search ok")
        self.claude_client = MagicMock()
        self.claude_client.process_email_content.return_value = "entity list"
        self.claude_client.chat.return_value = "summary text"

        memory_store = MagicMock()
        memory_store.memory_entries = []
        memory_store.add_memory_entry = MagicMock(return_value=True)

        bot = types.SimpleNamespace(
            gmail_client=self.gmail_client,
            claude_client=self.claude_client,
            system_message="sys",
            enhanced_memory_store=memory_store,
        )
        st_stub.session_state.bot = bot

    def tearDown(self):
        st_stub.session_state.__dict__.clear()

    def test_search_extract_summarize_and_log(self):
        state = {}
        step1 = {"action_type": "search_inbox", "parameters": {"query": "test"}, "output_key": "emails"}
        res1 = execute_step(step1, state)
        self.gmail_client.search_emails.assert_called_once()
        self.assertIn("emails", res1["updated_agentic_state"]["accumulated_results"])

        step2 = {
            "action_type": "extract_entities",
            "parameters": {"input_data_key": "emails", "extraction_prompt": "extract"},
            "output_key": "entities",
        }
        res2 = execute_step(step2, res1["updated_agentic_state"])
        self.claude_client.process_email_content.assert_called_once()
        self.assertIn("entities", res2["updated_agentic_state"]["accumulated_results"])

        step3 = {
            "action_type": "summarize_text",
            "parameters": {"input_data_key": "entities"},
            "output_key": "summary",
        }
        res3 = execute_step(step3, res2["updated_agentic_state"])
        self.claude_client.chat.assert_called_once()
        self.assertEqual(res3["updated_agentic_state"]["accumulated_results"]["summary"], "summary text")

        step4 = {
            "action_type": "log_to_notebook",
            "parameters": {"input_data_key": "summary", "section_title": "Notes"},
            "output_key": "log",
        }
        res4 = execute_step(step4, res3["updated_agentic_state"])
        st_stub.session_state.bot.enhanced_memory_store.add_memory_entry.assert_called_once()
        self.assertEqual(res4["status"], "success")


if __name__ == "__main__":
    unittest.main()
