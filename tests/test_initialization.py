import importlib
import sys
import types
import os
import contextlib
import pytest

from gmail_chatbot.email_config import CLAUDE_API_KEY_ENV

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)


def _create_streamlit_stub():
    st = types.SimpleNamespace()
    class SessionState(dict):
        def __getattr__(self, item):
            return self.get(item)

        def __setattr__(self, key, value):
            self[key] = value

    st.session_state = SessionState()

    def noop(*args, **kwargs):
        pass

    st.set_page_config = noop
    st.title = noop
    st.info = noop
    st.error = noop
    st.warning = noop
    st.success = noop
    st.toast = noop
    st.chat_input = lambda *a, **k: None
    st.chat_message = lambda *a, **k: contextlib.nullcontext()
    st.expander = lambda *a, **k: contextlib.nullcontext()

    class Sidebar:
        def header(self, *a, **k):
            pass

        def toggle(self, *a, **k):
            pass

        def number_input(self, *a, **k):
            pass

        def title(self, *a, **k):
            pass

        def checkbox(self, *a, **k):
            return False

        def button(self, *a, **k):
            return False

        def file_uploader(self, *a, **k):
            return None

        def subheader(self, *a, **k):
            pass

        def code(self, *a, **k):
            pass

        def error(self, *a, **k):
            pass

        def markdown(self, *a, **k):
            pass

        def caption(self, *a, **k):
            pass

    st.sidebar = Sidebar()

    @contextlib.contextmanager
    def spinner(*args, **kwargs):
        yield

    st.spinner = spinner

    def stop():
        raise RuntimeError("st.stop called")

    st.stop = stop
    return st


@pytest.fixture
def streamlit_stub(monkeypatch):
    st = _create_streamlit_stub()
    monkeypatch.setitem(sys.modules, "streamlit", st)
    yield st
    sys.modules.pop("streamlit", None)


@pytest.fixture
def dummy_email_main(monkeypatch):
    module = types.ModuleType("email_main")

    class DummyGmailChatbotApp:
        def __init__(self, *args, **kwargs):
            self.gmail_service = object()
            self.vector_search_available = True
            self.email_memory = object()
            self.claude_client = object()

        def test_gmail_api_connection(self):
            return True, "✓ Gmail API connection test successful"

        def get_vector_search_error_message(self):
            return None

    module.GmailChatbotApp = DummyGmailChatbotApp
    monkeypatch.setitem(sys.modules, "email_main", module)
    monkeypatch.setitem(sys.modules, "gmail_chatbot.email_main", module)
    yield module
    sys.modules.pop("email_main", None)


def _load_chat_app():
    import gmail_chatbot.email_config as email_config
    email_config.load_env = lambda *a, **k: None
    if "chat_app_st" in sys.modules:
        del sys.modules["chat_app_st"]
    return importlib.import_module("chat_app_st")


def test_initialize_chatbot_success(streamlit_stub, dummy_email_main):
    os.environ[CLAUDE_API_KEY_ENV] = "test-key"
    chat_app = _load_chat_app()
    streamlit_stub.session_state.clear()
    status = chat_app.initialize_chatbot()
    assert status is True
    steps = streamlit_stub.session_state.get("initialization_steps", [])
    joined = "\n".join(str(s) for s in steps)
    assert CLAUDE_API_KEY_ENV in joined
    assert "env" in joined or ".env" in joined
    assert "Gmail client" in joined
    assert "Vector search" in joined
    assert "Email memory" in joined


def test_initialize_chatbot_missing_api_key(streamlit_stub, dummy_email_main):
    os.environ[CLAUDE_API_KEY_ENV] = "temporary"
    _load_chat_app()
    streamlit_stub.session_state.clear()
    os.environ.pop(CLAUDE_API_KEY_ENV, None)
    chat_app = importlib.import_module("chat_app_st")
    with pytest.raises(RuntimeError):
        chat_app.initialize_chatbot()
    steps = streamlit_stub.session_state.get("initialization_steps", [])
    assert any("Missing" in str(s) for s in steps)
    assert streamlit_stub.session_state.get("bot_initialized_successfully") is False
