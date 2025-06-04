import sys
import types
import contextlib
from unittest.mock import MagicMock, patch
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


class SessionState(dict):
    def __getattr__(self, item):
        return self.get(item)

    def __setattr__(self, key, value):
        self[key] = value


def _create_streamlit_stub(prompt: str) -> types.ModuleType:
    st = types.ModuleType("streamlit")
    st.session_state = SessionState()
    st.chat_input = lambda *a, **k: prompt
    st.chat_message = contextlib.nullcontext
    st.set_page_config = lambda *a, **k: None
    st.title = lambda *a, **k: None
    st.progress = lambda *a, **k: types.SimpleNamespace(
        progress=lambda *a2, **k2: None
    )
    st.markdown = lambda *a, **k: None
    st.info = lambda *a, **k: None
    st.error = lambda *a, **k: None
    st.success = lambda *a, **k: None
    st.warning = lambda *a, **k: None
    st.balloons = lambda *a, **k: None
    st.stop = lambda *a, **k: None
    st.expander = lambda *a, **k: contextlib.nullcontext()

    @contextlib.contextmanager
    def spinner(*a, **k):
        yield

    st.spinner = spinner
    st.sidebar = types.SimpleNamespace(
        header=lambda *a, **k: None,
        toggle=lambda *a, **k: None,
        subheader=lambda *a, **k: None,
        number_input=lambda *a, **k: None,
        title=lambda *a, **k: None,
        checkbox=lambda *a, **k: False,
        file_uploader=lambda *a, **k: None,
        success=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        info=lambda *a, **k: None,
        write=lambda *a, **k: None,
        markdown=lambda *a, **k: None,
        caption=lambda *a, **k: None,
        expander=lambda *a, **k: contextlib.nullcontext(),
    )
    st.json = lambda *a, **k: None
    return st


def test_agentic_plan_fallback(monkeypatch):
    st_stub = _create_streamlit_stub("hi")
    sys.modules["streamlit"] = st_stub

    st_stub.session_state.agentic_mode_enabled = True
    st_stub.session_state.agentic_plan = None
    st_stub.session_state.bot_initialized_successfully = True

    dummy_bot = types.SimpleNamespace(
        chat_history=[],
        process_message=MagicMock(return_value="assistant reply"),
    )
    st_stub.session_state.bot = dummy_bot

    with patch("gmail_chatbot.agentic_planner.generate_plan", return_value=None):
        pass

    assert dummy_bot.process_message.called
    assert dummy_bot.chat_history == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "assistant reply"},
    ]

