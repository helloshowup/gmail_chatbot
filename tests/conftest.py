import sys
import types
import os
import contextlib
import pytest

# Mark that tests are running so application modules avoid altering sys.stdout/stderr
os.environ.setdefault("PYTEST_RUNNING", "1")

# Provide minimal stub modules if not installed
for mod_name in ['anthropic', 'joblib', 'numpy']:
    if mod_name not in sys.modules:
        stub = types.ModuleType(mod_name)
        if mod_name == 'joblib':
            stub.load = lambda *a, **k: {}
            stub.dump = lambda *a, **k: None
        if mod_name == 'numpy':
            def argmax(seq):
                return max(range(len(seq)), key=lambda i: seq[i])
            stub.argmax = argmax
            stub.array = lambda *a, **k: []
            stub.__version__ = '0.0'
        sys.modules[mod_name] = stub
from unittest.mock import MagicMock


class DummyClaudeClient:
    """Simple Claude client stub used for tests."""

    prep_model = "prep-model"

    def __init__(self, *a, **k):
        self.client = True

    def process_query(self, *a, **k):
        return "from:test@example.com"

    def chat(self, *a, **k):
        return MagicMock(content="Ack")

    def evaluate_vector_match(self, *a, **k):
        return "Found results"

# Minimal stubs for Google API modules
if 'google' not in sys.modules:
    google = types.ModuleType('google')
    google.auth = types.SimpleNamespace(
        exceptions=types.SimpleNamespace(RefreshError=Exception),
        transport=types.SimpleNamespace(requests=types.SimpleNamespace(Request=MagicMock()))
    )
    class DummyCredentials:
        def __init__(self, *a, **k):
            self.valid = True
            self.expired = False

        def refresh(self, *a, **k):
            pass

        @classmethod
        def from_authorized_user_file(cls, *a, **k):
            return cls()

    google.oauth2 = types.SimpleNamespace(credentials=types.SimpleNamespace(Credentials=DummyCredentials))
    sys.modules['google'] = google
    sys.modules['google.auth'] = google.auth
    sys.modules['google.auth.exceptions'] = google.auth.exceptions
    sys.modules['google.auth.transport'] = google.auth.transport
    sys.modules['google.auth.transport.requests'] = google.auth.transport.requests
    sys.modules['google.oauth2'] = google.oauth2
    sys.modules['google.oauth2.credentials'] = google.oauth2.credentials

    flow_module = types.ModuleType('google_auth_oauthlib.flow')
    flow_module.InstalledAppFlow = MagicMock()
    google_auth_oauthlib = types.ModuleType('google_auth_oauthlib')
    google_auth_oauthlib.flow = flow_module
    google_auth_oauthlib_module = google_auth_oauthlib
    sys.modules['google_auth_oauthlib'] = google_auth_oauthlib_module
    sys.modules['google_auth_oauthlib.flow'] = flow_module


    discovery_module = types.ModuleType('googleapiclient.discovery')
    discovery_module.build = MagicMock()
    errors_module = types.ModuleType('googleapiclient.errors')
    errors_module.HttpError = Exception
    googleapiclient = types.ModuleType('googleapiclient')
    googleapiclient.discovery = discovery_module
    googleapiclient.errors = errors_module
    sys.modules['googleapiclient'] = googleapiclient
    sys.modules['googleapiclient.discovery'] = discovery_module
    sys.modules['googleapiclient.errors'] = errors_module

    googleapiclient_module = types.ModuleType('googleapiclient')
    googleapiclient_module.discovery = discovery_module
    googleapiclient_module.errors = errors_module
    sys.modules['google_auth_oauthlib'] = google_auth_oauthlib_module
    sys.modules['google_auth_oauthlib.flow'] = flow_module
    sys.modules['googleapiclient'] = googleapiclient_module
    sys.modules['googleapiclient.discovery'] = discovery_module
    sys.modules['googleapiclient.errors'] = errors_module

# Minimal numpy stub for email_vector_db import
if 'numpy' not in sys.modules:
    numpy_module = types.ModuleType('numpy')
    numpy_module.array = lambda *a, **k: []
    sys.modules['numpy'] = numpy_module

# Ensure constants exist on email_vector_db for tests
try:
    import gmail_chatbot.email_vector_db as evdb
    from pathlib import Path
    if not hasattr(evdb, 'EMBEDDING_MODEL_NAME'):
        evdb.EMBEDDING_MODEL_NAME = 'test-embedding'
    if not hasattr(evdb, 'DEFAULT_CACHE_DIR'):
        evdb.DEFAULT_CACHE_DIR = Path('/tmp')
    if not hasattr(evdb, 'VECTOR_LIBS_AVAILABLE'):
        evdb.VECTOR_LIBS_AVAILABLE = False
except Exception:
    pass

from unittest.mock import MagicMock


@pytest.fixture(autouse=True)
def patch_external_clients(monkeypatch):
    """Patch heavy external client classes used during app initialization."""
    class DummyGmailClient:
        def __init__(self, *a, **k):
            self.service = MagicMock()

        def search_emails(self, *a, **k):
            return ([{"id": "1"}], "Found results")

    monkeypatch.setattr(
        "gmail_chatbot.app.core.GmailAPIClient",
        DummyGmailClient,
    )
    monkeypatch.setattr(
        "gmail_chatbot.app.core.ClaudeAPIClient",
        DummyClaudeClient,
    )
    monkeypatch.setattr(
        "gmail_chatbot.memory_handler.MemoryActionsHandler.perform_autonomous_memory_enrichment",
        lambda *a, **k: None,
    )
    yield

# Provide a basic streamlit stub with attribute-style session_state
if 'streamlit' not in sys.modules:
    st_stub = types.ModuleType('streamlit')
    class SessionState(dict):
        def __getattr__(self, item):
            return self.get(item)

        def __setattr__(self, key, value):
            self[key] = value

    st_stub.session_state = SessionState()
    st_stub.spinner = contextlib.nullcontext
    st_stub.toast = lambda *a, **k: None
    st_stub.set_page_config = lambda *a, **k: None
    st_stub.title = lambda *a, **k: None
    st_stub.chat_message = contextlib.nullcontext
    st_stub.chat_input = lambda *a, **k: None
    class Sidebar:
        def header(self, *a, **k):
            pass

        def toggle(self, *a, **k):
            pass

        def number_input(self, *a, **k):
            return 0

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

    st_stub.sidebar = Sidebar()
    sys.modules['streamlit'] = st_stub

# Ensure Anthropic API key placeholder exists for app initialization
try:
    from gmail_chatbot.email_config import CLAUDE_API_KEY_ENV
    os.environ.setdefault(CLAUDE_API_KEY_ENV, "test-key")
except Exception:
    pass
