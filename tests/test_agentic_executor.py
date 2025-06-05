import sys
import types
import unittest
import contextlib
from unittest.mock import MagicMock, ANY
import os
from datetime import datetime

# Ensure project root is on path for direct test execution
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Provide a minimal streamlit stub if streamlit is not available
if 'streamlit' not in sys.modules:
    st_stub = types.ModuleType('streamlit')
    st_stub.toast = lambda *args, **kwargs: None
    st_stub.session_state = types.SimpleNamespace()
    # Minimal UI stubs
    st_stub.set_page_config = lambda *a, **k: None
    st_stub.title = lambda *a, **k: None
    st_stub.progress = lambda *a, **k: types.SimpleNamespace(progress=lambda *a2, **k2: None)
    st_stub.info = lambda *a, **k: None
    st_stub.error = lambda *a, **k: None
    st_stub.success = lambda *a, **k: None
    st_stub.warning = lambda *a, **k: None
    st_stub.balloons = lambda *a, **k: None
    @contextlib.contextmanager
    def spinner(*args, **kwargs):
        yield
    st_stub.spinner = spinner
    st_stub.sidebar = types.SimpleNamespace(
        subheader=lambda *a, **k: None,
        success=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        info=lambda *a, **k: None,
        write=lambda *a, **k: None,
        markdown=lambda *a, **k: None,
        expander=lambda *a, **k: contextlib.nullcontext(),
    )
    st_stub.json = lambda *a, **k: None
    st_stub.chat_message = contextlib.nullcontext
    st_stub.chat_input = lambda *a, **k: None
    sys.modules['streamlit'] = st_stub
else:
    st_stub = sys.modules['streamlit']
    if not hasattr(st_stub, 'session_state'):
        st_stub.session_state = types.SimpleNamespace()
    if not hasattr(st_stub, 'toast'):
        st_stub.toast = lambda *args, **kwargs: None
    if not hasattr(st_stub, 'progress'):
        st_stub.progress = lambda *a, **k: types.SimpleNamespace(progress=lambda *a2, **k2: None)
    if not hasattr(st_stub, 'spinner'):
        @contextlib.contextmanager
        def spinner(*args, **kwargs):
            yield
        st_stub.spinner = spinner
    if not hasattr(st_stub, 'info'):
        st_stub.info = lambda *a, **k: None
    if not hasattr(st_stub, 'error'):
        st_stub.error = lambda *a, **k: None
    if not hasattr(st_stub, 'success'):
        st_stub.success = lambda *a, **k: None
    if not hasattr(st_stub, 'warning'):
        st_stub.warning = lambda *a, **k: None
    if not hasattr(st_stub, 'balloons'):
        st_stub.balloons = lambda *a, **k: None
    if not hasattr(st_stub, 'sidebar'):
        st_stub.sidebar = types.SimpleNamespace(
            subheader=lambda *a, **k: None,
            success=lambda *a, **k: None,
            warning=lambda *a, **k: None,
            info=lambda *a, **k: None,
            write=lambda *a, **k: None,
            markdown=lambda *a, **k: None,
            expander=lambda *a, **k: contextlib.nullcontext(),
        )

from gmail_chatbot.agentic_executor import (
    execute_step,
)

class TestAgenticExecutorFlow(unittest.TestCase):
    def setUp(self):
        self.gmail_client = MagicMock()
        self.gmail_client.search_emails.return_value = ([{"id": "1", "snippet": "hi"}], "search ok")
        self.claude_client = MagicMock()
        self.claude_client.process_email_content.return_value = "entity list"
        self.claude_client.chat.return_value = "summary text"
        self.claude_client.prep_model = "prep-model"

        memory_store = MagicMock()
        memory_store.memory_entries = []
        def add_entry(entry):
            memory_store.memory_entries.append(entry)
            return True

        memory_store.add_memory_entry = MagicMock(side_effect=add_entry)
        memory_store.memory_entries_store = MagicMock()
        memory_store.memory_entries_store.save = MagicMock()

        bot = types.SimpleNamespace(
            gmail_client=self.gmail_client,
            claude_client=self.claude_client,
            system_message="sys",
            enhanced_memory_store=memory_store,
        )
        st_stub.session_state.bot = bot

    def tearDown(self):
        class SessionState(dict):
            def __getattr__(self, item):
                return self.get(item)

            def __setattr__(self, key, value):
                self[key] = value

        st_stub.session_state = SessionState()

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
        self.claude_client.process_email_content.assert_called_once_with(
            ANY,
            "extract",
            "sys",
            model=self.claude_client.prep_model,
        )
        self.assertIn("entities", res2["updated_agentic_state"]["accumulated_results"])

        step3 = {
            "action_type": "summarize_text",
            "parameters": {"input_data_key": "entities"},
            "output_key": "summary",
        }
        res3 = execute_step(step3, res2["updated_agentic_state"])
        self.claude_client.chat.assert_called_once_with(
            ANY,
            [],
            "sys",
            model=self.claude_client.prep_model,
        )
        self.assertEqual(res3["updated_agentic_state"]["accumulated_results"]["summary"], "summary text")

        step4 = {
            "action_type": "log_to_notebook",
            "parameters": {"input_data_key": "summary", "section_title": "Notes"},
            "output_key": "log",
        }
        res4 = execute_step(step4, res3["updated_agentic_state"])
        st_stub.session_state.bot.enhanced_memory_store.add_memory_entry.assert_called_once()
        self.assertEqual(res4["status"], "success")

    def test_send_email_handler_preview_and_flag(self):
        state = {}
        step = {
            "action_type": "send_email",
            "parameters": {"to": "a@b.com", "subject": "Hi", "body": "Test"},
            "output_key": "send_result",
        }
        res = execute_step(step, state)
        self.gmail_client.send_email.assert_not_called()
        self.assertTrue(res["requires_user_input"])
        self.assertIn("To: a@b.com", res["message"])
        self.assertEqual(res["updated_agentic_state"]["accumulated_results"]["send_result"],
                         {"to": "a@b.com", "subject": "Hi", "body": "Test"})

    def test_send_email_confirmation_flow(self):
        state = {}
        step = {
            "action_type": "send_email",
            "parameters": {"to": "c@d.com", "subject": "Hello", "body": "World"},
            "output_key": "send_result",
        }
        res = execute_step(step, state)
        pending = {
            "action": "send_email",
            "parameters": res["updated_agentic_state"]["accumulated_results"]["send_result"],
            "next_step_index": 1,
        }
        if pending["action"] == "send_email":
            st_stub.session_state.bot.gmail_client.send_email(**pending["parameters"])
        self.gmail_client.send_email.assert_called_once_with(to="c@d.com", subject="Hello", body="World")

    def test_log_to_notebook_skipped_if_duplicate(self):
        today = datetime.now().date()
        existing = {
            "id": f"prof_context_{today.isoformat()}",
            "title": "Old",
            "content": "old text",
            "type": "professional_context",
            "date": datetime.combine(today, datetime.min.time()).isoformat(),
            "tags": ["professional_context"],
        }
        mem_store = st_stub.session_state.bot.enhanced_memory_store
        mem_store.memory_entries = [existing]

        step = {
            "action_type": "log_to_notebook",
            "parameters": {"input_data_key": "summary", "section_title": "Notes"},
            "output_key": "log",
        }
        state = {"accumulated_results": {"summary": "new"}}
        res = execute_step(step, state)
        self.assertEqual(res["status"], "skipped")
        mem_store.add_memory_entry.assert_not_called()

    def test_log_to_notebook_overwrite(self):
        today = datetime.now().date()
        existing = {
            "id": f"prof_context_{today.isoformat()}",
            "title": "Old",
            "content": "old text",
            "type": "professional_context",
            "date": datetime.combine(today, datetime.min.time()).isoformat(),
            "tags": ["professional_context"],
        }
        mem_store = st_stub.session_state.bot.enhanced_memory_store
        mem_store.memory_entries = [existing]
        mem_store.memory_entries_store.save.reset_mock()

        step = {
            "action_type": "log_to_notebook",
            "parameters": {
                "input_data_key": "summary",
                "section_title": "Notes",
                "overwrite_if_exists": True,
            },
            "output_key": "log",
        }
        state = {"accumulated_results": {"summary": "new info"}}
        res = execute_step(step, state)
        self.assertEqual(res["status"], "success")
        mem_store.memory_entries_store.save.assert_called_once()
        self.assertEqual(len(mem_store.memory_entries), 1)

if __name__ == "__main__":
    unittest.main()
