import sys
import types
import unittest
import contextlib
from unittest.mock import MagicMock

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

from agentic_executor import execute_step, handle_step_limit_reached
import agentic_executor

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

    def test_sequential_plan_execution(self):
        plan = [
            {
                "step_id": "test_search_step",
                "description": "Step 1",
                "action_type": "placeholder_search_tool",
                "parameters": {"query": "agentic"},
                "output_key": "search_results",
            },
            {
                "step_id": "test_summarize_step",
                "description": "Step 2",
                "action_type": "placeholder_summarize_tool",
                "parameters": {"input_data_key": "search_results"},
                "output_key": "summary",
            },
        ]

        state: dict = {}
        for step in plan:
            res = execute_step(step, state)
            state = res["updated_agentic_state"]

        self.assertIn("summary", state.get("accumulated_results", {}))
        self.assertEqual(
            state["accumulated_results"]["summary"],
            "Simulated summary of 1 documents.",
        )


class TestHandleStepLimitReached(unittest.TestCase):
    def setUp(self):
        st_stub.button = MagicMock(return_value=False)
        st_stub.warning = MagicMock()

    def tearDown(self):
        st_stub.session_state.__dict__.clear()

    def test_continue_choice_resets_count(self):
        st_stub.button = MagicMock(side_effect=[True, False])
        agentic_state = {"executed_call_count": 5}
        with unittest.mock.patch.object(agentic_executor, "summarize_and_log_agentic_results") as summary_mock:
            choice = handle_step_limit_reached(agentic_state, 5)
        self.assertEqual(choice, "continue")
        self.assertEqual(agentic_state["executed_call_count"], 0)
        summary_mock.assert_not_called()

    def test_stop_choice_triggers_summary(self):
        st_stub.button = MagicMock(side_effect=[False, True])
        agentic_state = {"executed_call_count": 5}
        with unittest.mock.patch.object(agentic_executor, "summarize_and_log_agentic_results") as summary_mock:
            choice = handle_step_limit_reached(agentic_state, 5)
        self.assertEqual(choice, "stop")
        summary_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
