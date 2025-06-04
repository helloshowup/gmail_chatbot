import sys
import types
import contextlib
from unittest.mock import MagicMock

# Ensure project root on path
import os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Provide streamlit stub
if 'streamlit' not in sys.modules:
    import contextlib
    st_stub = types.ModuleType('streamlit')
    st_stub.toast = lambda *a, **k: None
    class SessionState(dict):
        def __getattr__(self, item):
            return self.get(item)

        def __setattr__(self, key, value):
            self[key] = value

    st_stub.session_state = SessionState()
    st_stub.set_page_config = lambda *a, **k: None
    st_stub.title = lambda *a, **k: None
    st_stub.progress = lambda *a, **k: types.SimpleNamespace(progress=lambda *a2, **k2: None)
    st_stub.info = lambda *a, **k: None
    st_stub.error = lambda *a, **k: None
    st_stub.success = lambda *a, **k: None
    st_stub.warning = lambda *a, **k: None
    st_stub.balloons = lambda *a, **k: None
    st_stub.stop = lambda *a, **k: None
    st_stub.expander = lambda *a, **k: contextlib.nullcontext()
    @contextlib.contextmanager
    def spinner(*a, **k):
        yield
    st_stub.spinner = spinner
    st_stub.sidebar = types.SimpleNamespace(
        header=lambda *a, **k: None,
        toggle=lambda *a, **k: None,
        subheader=lambda *a, **k: None,
        number_input=lambda *a, **k: None,
        title=lambda *a, **k: None,
        checkbox=lambda *a, **k: False,
        button=lambda *a, **k: None,
        file_uploader=lambda *a, **k: None,
        success=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        info=lambda *a, **k: None,
        write=lambda *a, **k: None,
        markdown=lambda *a, **k: None,
        caption=lambda *a, **k: None,
        expander=lambda *a, **k: contextlib.nullcontext(),
    )
    st_stub.json = lambda *a, **k: None
    st_stub.chat_message = contextlib.nullcontext
    st_stub.chat_input = lambda *a, **k: None
    sys.modules['streamlit'] = st_stub
else:
    st_stub = sys.modules['streamlit']
    if not hasattr(st_stub, 'session_state') or not isinstance(st_stub.session_state, dict):
        class SessionState(dict):
            def __getattr__(self, item):
                return self.get(item)

            def __setattr__(self, key, value):
                self[key] = value

        st_stub.session_state = SessionState()
    # Ensure required attributes exist
    if not hasattr(st_stub, 'sidebar'):
        st_stub.sidebar = types.SimpleNamespace()
    sidebar = st_stub.sidebar
    for attr in ['header', 'toggle', 'subheader', 'number_input', 'title', 'checkbox',
                 'button', 'file_uploader', 'success', 'warning', 'info', 'write',
                 'markdown', 'caption', 'expander']:
        if not hasattr(sidebar, attr):
            setattr(sidebar, attr, (lambda *a, **k: None) if attr != 'expander' else (lambda *a, **k: contextlib.nullcontext()))
    for attr in ['toast', 'set_page_config', 'title', 'progress', 'info', 'error',
                 'success', 'warning', 'balloons', 'stop', 'expander', 'json',
                 'chat_message', 'chat_input']:
        if not hasattr(st_stub, attr):
            if attr in ['progress']:
                setattr(st_stub, attr, lambda *a, **k: types.SimpleNamespace(progress=lambda *a2, **k2: None))
            elif attr == 'expander':
                setattr(st_stub, attr, lambda *a, **k: contextlib.nullcontext())
            else:
                setattr(st_stub, attr, lambda *a, **k: None)

import chat_app_st
from gmail_chatbot.app.core import GmailChatbotApp


def test_task_chain_flow(monkeypatch):
    """Confirm TASK_CHAIN plan executes after user confirmation."""
    # Prepare Streamlit session state
    st_stub.session_state.agentic_mode_enabled = False
    st_stub.session_state.agentic_state = {
        'current_step_index': 0,
        'executed_call_count': 0,
        'accumulated_results': {},
        'error_messages': []
    }
    st_stub.session_state.agentic_step_limit = 5
    st_stub.session_state.agentic_plan = None

    # Build minimal GmailChatbotApp instance without running __init__
    app = GmailChatbotApp.__new__(GmailChatbotApp)
    app.memory_actions_handler = MagicMock()
    app.memory_actions_handler.perform_autonomous_memory_enrichment = MagicMock()
    app.memory_actions_handler.get_pending_proactive_summaries.return_value = []
    app.memory_actions_handler.record_interaction_in_memory = MagicMock()
    app.preference_detector = MagicMock(process_message=MagicMock(return_value=(False, None)))
    app.handle_pending_email_menu = MagicMock(return_value=None)
    app.claude_client = MagicMock()
    app.gmail_client = MagicMock()
    app.memory_store = MagicMock()
    app.system_message = ""
    app.counter = {"autonomous_task_counter": 0}
    app.autonomous_task_counter = 0
    app.pending_email_context = None

    # Simulate prior assistant message containing a TASK_CHAIN plan
    plan_text = (
        "TASK_CHAIN: 1. Search inbox for details about Bryce Hepburn\n"
        "2. Summarize the findings.\nWould you like me to proceed?"
    )
    app.chat_history = [
        {"role": "user", "content": "Find info"},
        {"role": "assistant", "content": plan_text},
    ]
    # Current user confirmation will be appended as in process_message
    app.chat_history.append({"role": "user", "content": "yes"})

    # Structured plan returned by parse_task_chain
    plan = [
        {
            "step_id": "step1",
            "description": "Search inbox for details about Bryce Hepburn",
            "action_type": "search_inbox",
            "parameters": {"query": "bryce hepburn"},
            "output_key": "emails",
        },
        {
            "step_id": "step2",
            "description": "Summarize the findings",
            "action_type": "summarize_text",
            "parameters": {"input_data_key": "emails"},
            "output_key": "summary",
        },
    ]
    monkeypatch.setattr('gmail_chatbot.app.core.parse_task_chain', lambda text: plan)

    # Capture execute_step calls
    calls = []

    def fake_execute_step(step, state):
        calls.append(step)
        new_state = state.copy()
        new_state.setdefault('accumulated_results', {})
        new_state['accumulated_results'][step['output_key']] = f"result_{step['step_id']}"
        return {
            'status': 'success',
            'message': 'ok',
            'updated_agentic_state': new_state,
            'requires_user_input': False,
        }

    monkeypatch.setattr('gmail_chatbot.agentic_executor.execute_step', fake_execute_step)

    # Simple plan runner to avoid full Streamlit loop
    def simple_run_agentic_plan():
        pl = st_stub.session_state.agentic_plan
        state = st_stub.session_state.agentic_state
        for idx, step in enumerate(pl):
            res = fake_execute_step(step, state)
            state = res['updated_agentic_state']
            state['current_step_index'] = idx + 1
            state['executed_call_count'] = state.get('executed_call_count', 0) + 1
            st_stub.session_state.agentic_state = state
        st_stub.session_state.agentic_plan = None

    monkeypatch.setattr(chat_app_st, 'run_agentic_plan', simple_run_agentic_plan)

    # User confirms the task chain
    response = app.handle_confirmation('yes', 'yes', 'req123')
    assert 'starting' in response.lower()

    # Validate execute_step calls and session state
    assert len(calls) == len(plan)
    assert calls[0]['parameters']['query'] == 'bryce hepburn'
    assert st_stub.session_state.agentic_state['current_step_index'] == len(plan)
    assert st_stub.session_state.agentic_state['executed_call_count'] == len(plan)
