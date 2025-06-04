import sys
import types
import os

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

# Minimal stubs for Google API modules
if 'google' not in sys.modules:
    google = types.ModuleType('google')
    google.auth = types.SimpleNamespace(
        exceptions=types.SimpleNamespace(RefreshError=Exception),
        transport=types.SimpleNamespace(requests=types.SimpleNamespace(Request=MagicMock()))
    )
    google.oauth2 = types.SimpleNamespace(credentials=types.SimpleNamespace(Credentials=MagicMock()))
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
