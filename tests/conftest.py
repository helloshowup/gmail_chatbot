import sys
import os
import types
from unittest.mock import MagicMock

# Indicate that tests are running
os.environ.setdefault("PYTEST_RUNNING", "1")

# Provide stub modules for external dependencies not available in the test env
if 'anthropic' not in sys.modules:
    anthropic_module = types.ModuleType('anthropic')
    anthropic_module.Anthropic = MagicMock()
    anthropic_module.Client = MagicMock()
    sys.modules['anthropic'] = anthropic_module

if 'joblib' not in sys.modules:
    joblib_module = types.ModuleType('joblib')
    joblib_module.load = MagicMock()
    joblib_module.dump = MagicMock()
    sys.modules['joblib'] = joblib_module

# Stub google modules used by Gmail API client if missing
if 'google' not in sys.modules:
    google_auth_exceptions = types.SimpleNamespace(RefreshError=Exception)
    google_auth_transport = types.SimpleNamespace(requests=types.SimpleNamespace(Request=object))
    google_auth = types.SimpleNamespace(exceptions=google_auth_exceptions, transport=google_auth_transport)
    google_module = types.SimpleNamespace(auth=google_auth, oauth2=types.SimpleNamespace(credentials=types.SimpleNamespace(Credentials=object)))
    sys.modules['google'] = google_module
    sys.modules['google.oauth2'] = google_module.oauth2
    sys.modules['google.oauth2.credentials'] = google_module.oauth2.credentials
    sys.modules['google.auth'] = google_auth
    sys.modules['google.auth.exceptions'] = google_auth_exceptions
    sys.modules['google.auth.transport'] = google_auth_transport
    sys.modules['google.auth.transport.requests'] = google_auth_transport.requests

    flow_module = types.ModuleType('google_auth_oauthlib.flow')
    flow_module.InstalledAppFlow = MagicMock()
    google_auth_oauthlib_module = types.ModuleType('google_auth_oauthlib')
    google_auth_oauthlib_module.flow = flow_module
    discovery_module = types.ModuleType('googleapiclient.discovery')
    discovery_module.build = MagicMock()
    errors_module = types.ModuleType('googleapiclient.errors')
    errors_module.HttpError = Exception
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
