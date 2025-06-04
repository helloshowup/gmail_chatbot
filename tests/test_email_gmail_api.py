import unittest
from unittest.mock import patch, MagicMock  # Restore ANY
import os  # Restore os
import sys  # Restore sys
import ssl  # For ssl.SSLError
import logging  # For disabling/enabling logger in tests
import json  # For creating mock client_secret file
from pathlib import Path  # For type checking in mocks
import types

try:
    from google.oauth2.credentials import Credentials  # type: ignore
    import google.auth.exceptions as _  # type: ignore # noqa: F401
    import google.auth.transport.requests as _  # type: ignore # noqa: F401
    import google_auth_oauthlib.flow as _  # type: ignore # noqa: F401
    import googleapiclient.discovery as _  # type: ignore # noqa: F401
except ModuleNotFoundError:
    # Create minimal stub modules so that patch() calls work without the real packages
    class Credentials:
        def __init__(self, *args, **kwargs):
            self.valid = True
            self.expired = False

        def refresh(self, *args, **kwargs):
            pass

        @classmethod
        def from_authorized_user_file(cls, *args, **kwargs):
            return cls()

    class RefreshError(Exception):
        pass

    class Request:
        pass

    google_auth_exceptions = types.SimpleNamespace(RefreshError=RefreshError)
    google_auth_transport = types.SimpleNamespace(requests=types.SimpleNamespace(Request=Request))
    google_auth = types.SimpleNamespace(exceptions=google_auth_exceptions, transport=google_auth_transport)
    google_module = types.SimpleNamespace(auth=google_auth, oauth2=types.SimpleNamespace(credentials=types.SimpleNamespace(Credentials=Credentials)))

    flow_module = types.ModuleType("google_auth_oauthlib.flow")
    flow_module.InstalledAppFlow = MagicMock()
    google_auth_oauthlib_module = types.ModuleType("google_auth_oauthlib")
    google_auth_oauthlib_module.flow = flow_module

    discovery_module = types.ModuleType("googleapiclient.discovery")
    discovery_module.build = MagicMock()

    errors_module = types.ModuleType("googleapiclient.errors")
    class HttpError(Exception):
        pass
    errors_module.HttpError = HttpError

    googleapiclient_module = types.ModuleType("googleapiclient")
    googleapiclient_module.discovery = discovery_module
    googleapiclient_module.errors = errors_module

    anthropic_module = types.ModuleType("anthropic")
    anthropic_module.Client = MagicMock()

    sys.modules.setdefault("google", google_module)
    sys.modules.setdefault("google.oauth2", google_module.oauth2)
    sys.modules.setdefault("google.oauth2.credentials", google_module.oauth2.credentials)
    sys.modules.setdefault("google.auth", google_module.auth)
    sys.modules.setdefault("google.auth.exceptions", google_auth_exceptions)
    sys.modules.setdefault("google.auth.transport", google_auth_transport)
    sys.modules.setdefault("google.auth.transport.requests", google_auth_transport.requests)
    sys.modules.setdefault("google_auth_oauthlib", google_auth_oauthlib_module)
    sys.modules.setdefault("google_auth_oauthlib.flow", flow_module)
    sys.modules.setdefault("googleapiclient", googleapiclient_module)
    sys.modules.setdefault("googleapiclient.discovery", discovery_module)
    sys.modules.setdefault("googleapiclient.errors", errors_module)
    sys.modules.setdefault("anthropic", anthropic_module)

    # Indicate to application code that tests are running
    os.environ.setdefault("PYTEST_RUNNING", "1")

# Adjust sys.path to include the project root ('showup-tools')
project_root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root_dir not in sys.path:
    sys.path.insert(0, project_root_dir)

from gmail_chatbot.email_gmail_api import GmailAPIClient

# Define mock paths for constants used by GmailAPIClient constructor
# These will be created and removed in setUp/tearDown
TEST_CLIENT_SECRET_FILE = "test_client_secret.json"
TEST_TOKEN_FILE = "test_token.json" 

class TestGmailAPIClientSSLErrors(unittest.TestCase):
    def setUp(self):
        # Create a dummy client_secret.json for tests that instantiate GmailAPIClient
        # The content needs to be valid JSON for InstalledAppFlow.from_client_secrets_file
        mock_secret_content = {
            "installed": {
                "client_id": "mock_client_id",
                "project_id": "mock_project_id",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_secret": "mock_client_secret",
                "redirect_uris": ["http://localhost"]
            }
        }
        with open(TEST_CLIENT_SECRET_FILE, 'w') as f:
            json.dump(mock_secret_content, f)

        self.mock_claude_client = MagicMock()
        self.mock_claude_client.prep_model = "prep-model"
        self.mock_system_message = "Test system message"
    
    def tearDown(self):
        if os.path.exists(TEST_CLIENT_SECRET_FILE):
            os.remove(TEST_CLIENT_SECRET_FILE)
        if os.path.exists(TEST_TOKEN_FILE): # In case any test creates it
            os.remove(TEST_TOKEN_FILE)

    def test_authenticate_ssl_error_on_build(self):
        """Test SSL error during service build in _authenticate."""
        # Disable googleapiclient logging to see if it's involved in the TypeError
        google_api_logger = logging.getLogger('googleapiclient')
        original_level = google_api_logger.getEffectiveLevel()
        google_api_logger.setLevel(logging.CRITICAL + 1)

        self.addCleanup(google_api_logger.setLevel, original_level) 

        with patch('pathlib.Path.mkdir') as mock_mkdir, \
             patch('os.path.exists') as mock_os_path_exists, \
             patch('builtins.open', new_callable=MagicMock) as mock_open, \
             patch('google.auth.transport.requests.Request') as mock_google_request, \
             patch('pickle.load') as mock_pickle_load, \
             patch('gmail_chatbot.email_gmail_api.build') as mock_build, \
             patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file') as mock_flow_from_secrets:

            mock_mkdir.return_value = None

            def mock_exists_logic(path_arg):
                if isinstance(path_arg, Path) and path_arg.name == 'token.json': 
                    return True
                return False 
            mock_os_path_exists.side_effect = mock_exists_logic

            mock_loaded_credentials = MagicMock(spec=Credentials)
            mock_loaded_credentials.valid = True
            # Let other attributes be default MagicMocks. The path taken should only rely on .valid.
            mock_pickle_load.return_value = mock_loaded_credentials

            # mock_flow_from_secrets is patched, its default MagicMock return is fine.

            # Mock build to raise an SSL error with an explicit errno
            mock_build.side_effect = ssl.SSLError("Simulated SSL Error during build")

            # Import the class and constants to be tested/used from within the patch context
            # to ensure we are using the potentially reloaded module where 'build' is patched.
            from gmail_chatbot.email_gmail_api import (
                GmailAPIClient,
            )

            # Attempt to instantiate the client. If DATA_DIR.mkdir was the issue at import,
            # this might now proceed further.
            with self.assertRaisesRegex(ValueError, "SSL Error building Gmail service.*Simulated SSL Error during build"):
                # The initial import of GmailAPIClient at the top of the file should now hopefully succeed
                # due to mock_mkdir preventing issues with DATA_DIR creation at import time.
                client = GmailAPIClient(
                    claude_client=self.mock_claude_client, 
                    system_message=self.mock_system_message
                )
            mock_build.assert_called_once()

    def test_authenticate_ssl_error_on_refresh(self):
        """Test SSL error during credential refresh in _authenticate."""
        google_api_logger = logging.getLogger('googleapiclient')
        original_level = google_api_logger.getEffectiveLevel()
        google_api_logger.setLevel(logging.CRITICAL + 1)
        self.addCleanup(google_api_logger.setLevel, original_level)

        with patch('pathlib.Path.mkdir') as mock_mkdir, \
             patch('os.path.exists') as mock_os_path_exists, \
             patch('builtins.open', new_callable=MagicMock) as mock_open_file, \
             patch('google.auth.transport.requests.Request') as mock_google_request, \
             patch('pickle.load') as mock_pickle_load, \
             patch('pickle.dump') as mock_pickle_dump, \
             patch('gmail_chatbot.email_gmail_api.build') as mock_build, \
             patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file') as mock_flow_from_secrets:

            mock_mkdir.return_value = None

            def mock_exists_logic(path_arg):
                # Assuming GMAIL_TOKEN_FILE is 'token.json' as in the previous test
                if isinstance(path_arg, Path) and path_arg.name == 'token.json':
                    return True
                return False
            mock_os_path_exists.side_effect = mock_exists_logic

            # Simulate existing, but expired, credentials that need refresh
            mock_expired_credentials = MagicMock(spec=Credentials)
            mock_expired_credentials.valid = False
            mock_expired_credentials.expired = True
            mock_expired_credentials.refresh_token = "dummy_refresh_token"
            # Mock the refresh method to raise an SSLError
            mock_expired_credentials.refresh.side_effect = ssl.SSLError("Simulated SSL Error during refresh")
            
            mock_pickle_load.return_value = mock_expired_credentials

            # Create a specific mock for the Request() instance
            specific_request_instance = MagicMock()
            mock_google_request.return_value = specific_request_instance # Ensure Request() returns our specific mock

            # Import GmailAPIClient and relevant constants within the patch context
            from gmail_chatbot.email_gmail_api import (
                GmailAPIClient,
                DATA_DIR,
                GMAIL_TOKEN_FILE,
            )

            with self.assertRaisesRegex(ValueError, "SSL Error refreshing credentials.*Simulated SSL Error during refresh"):
                client = GmailAPIClient(
                    claude_client=self.mock_claude_client,
                    system_message=self.mock_system_message
                )
        
            mock_expired_credentials.refresh.assert_called_once_with(specific_request_instance)
            mock_pickle_dump.assert_not_called()
            mock_build.assert_not_called()
            
            # Check that open was called for reading the token
            expected_token_path = DATA_DIR / GMAIL_TOKEN_FILE
            mock_open_file.assert_any_call(expected_token_path, 'rb')

            # Ensure open was not called for writing the token
            found_write_call = False
            for call_obj in mock_open_file.call_args_list:
                args = call_obj.args
                if len(args) > 1 and args[1] == 'wb': 
                    found_write_call = True
                    break
            self.assertFalse(found_write_call, f"Token file should not have been opened for writing ('wb' mode). Calls: {mock_open_file.call_args_list}")

    def test_authenticate_ssl_error_on_refresh_then_flow_fails(self):
        """Test SSL on refresh, then flow fails, leading to auth failure."""
        with patch('gmail_chatbot.email_gmail_api.GMAIL_CLIENT_SECRET_FILE', TEST_CLIENT_SECRET_FILE) as mock_gcsf_const, \
             patch('gmail_chatbot.email_gmail_api.GMAIL_TOKEN_FILE', TEST_TOKEN_FILE) as mock_gtf_const, \
             patch('googleapiclient.discovery.build') as mock_build, \
             patch('google.oauth2.credentials.Credentials.from_authorized_user_file') as mock_creds_from_file, \
             patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file') as mock_flow_from_secrets:

            mock_credentials = MagicMock(spec=Credentials)
            mock_credentials.valid = False
            mock_credentials.expired = True
            mock_credentials.refresh_token = "fake_refresh_token"
            mock_credentials.refresh.side_effect = ssl.SSLError("Simulated SSL Error during refresh")
            mock_creds_from_file.return_value = mock_credentials

            mock_flow_instance = mock_flow_from_secrets.return_value
            mock_flow_instance.run_local_server.side_effect = ValueError("Flow aborted by test during re-auth")

            with self.assertRaisesRegex(ValueError, "Flow aborted by test during re-auth"):
                GmailAPIClient(
                    claude_client=self.mock_claude_client,
                    system_message=self.mock_system_message
                )

            mock_build.assert_not_called()

#    @patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file')
#    @patch('google.oauth2.credentials.Credentials.from_authorized_user_file')
#    @patch('googleapiclient.discovery.build')
#    @patch('gmail_chatbot.email_gmail_api.GMAIL_TOKEN_FILE', TEST_TOKEN_FILE)
#    @patch('gmail_chatbot.email_gmail_api.GMAIL_CLIENT_SECRET_FILE', TEST_CLIENT_SECRET_FILE)
#    def test_connection_ssl_error(self, mock_gcsf_const, mock_gtf_const, mock_build, mock_creds_from_file, mock_flow_from_secrets):
#        """Test test_connection handles SSL error."""
#        mock_service_instance = MagicMock()
#        mock_service_instance.users().getProfile().execute.side_effect = ssl.SSLError("Simulated SSL Error on getProfile")
#        mock_build.return_value = mock_service_instance
#        mock_creds_from_file.return_value = MagicMock(spec=Credentials, valid=True, expired=False)
#
#        # InstalledAppFlow is now patched at the method level by mock_flow_from_secrets
#        # mock_flow_from_secrets.from_client_secrets_file.return_value.run_local_server.return_value = MagicMock(spec=Credentials) # Example configuration
#        client = GmailAPIClient(
#            claude_client=self.mock_claude_client, 
#            system_message=self.mock_system_message
#        )
#        result = client.test_connection()
#        self.assertFalse(result['success'])
#        self.assertEqual(result['error_type'], 'ssl_error')
#        self.assertIn("Simulated SSL Error on getProfile", result['message'])

#    @patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file')
#    @patch('google.oauth2.credentials.Credentials.from_authorized_user_file')
#    @patch('googleapiclient.discovery.build')
#    @patch('gmail_chatbot.email_gmail_api.GMAIL_TOKEN_FILE', TEST_TOKEN_FILE)
#    @patch('gmail_chatbot.email_gmail_api.GMAIL_CLIENT_SECRET_FILE', TEST_CLIENT_SECRET_FILE)
#    def test_search_emails_ssl_error_on_list(self, mock_gcsf_const, mock_gtf_const, mock_build, mock_creds_from_file, mock_flow_from_secrets):
#        mock_service_instance = MagicMock()
#        mock_service_instance.users().messages().list().execute.side_effect = ssl.SSLError("SSL list error")
#        mock_build.return_value = mock_service_instance
#        mock_creds_from_file.return_value = MagicMock(spec=Credentials, valid=True, expired=False)
#
#        # InstalledAppFlow is now patched at the method level by mock_flow_from_secrets
#        client = GmailAPIClient(self.mock_claude_client, self.mock_system_message)
#        
#        emails, error_msg = client.search_emails("test query")
#        self.assertIsNone(emails)
#        self.assertIsNotNone(error_msg)
#        self.assertIn("SSL error during email search (listing messages): SSL list error", error_msg)

#    @patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file')
#    @patch('google.oauth2.credentials.Credentials.from_authorized_user_file')
#    @patch('googleapiclient.discovery.build')
#    @patch('gmail_chatbot.email_gmail_api.GMAIL_TOKEN_FILE', TEST_TOKEN_FILE)
#    @patch('gmail_chatbot.email_gmail_api.GMAIL_CLIENT_SECRET_FILE', TEST_CLIENT_SECRET_FILE)
#    def test_search_emails_ssl_error_on_get_skips(self, mock_gcsf_const, mock_gtf_const, mock_build, mock_creds_from_file, mock_flow_from_secrets):
#        mock_service_instance = MagicMock()
#        mock_service_instance.users().messages().list().execute.return_value = {
#            'messages': [{'id': 'id1', 'threadId': 'thread1'}, {'id': 'id2', 'threadId': 'thread2'}],
#            'resultSizeEstimate': 2
#        }
#        
#        # Mock the 'get' method on the messages resource
#        mock_messages_resource = mock_service_instance.users().messages()
#        mock_get_method = MagicMock()
#        mock_get_method.execute.side_effect = [
#            ssl.SSLError("SSL get error for id1"),
#            {'id': 'id2', 'snippet': 'Test email 2', 'payload': {'headers': [{'name': 'Subject', 'value': 'Subject 2'}]}}
#        ]
#        mock_messages_resource.get = mock_get_method # Attach the mock 'get' to the messages resource
#        
#        mock_build.return_value = mock_service_instance
#        mock_creds_from_file.return_value = MagicMock(spec=Credentials, valid=True, expired=False)
#
#        # InstalledAppFlow is now patched at the method level by mock_flow_from_secrets
#        client = GmailAPIClient(self.mock_claude_client, self.mock_system_message)
#        
#        with patch('gmail_chatbot.email_gmail_api.logging') as mock_logging:
#            emails, error_msg = client.search_emails("test query", max_results=2)
#            self.assertIsNone(error_msg, "Overall search should not report an error if some emails are processed")
#            self.assertIsNotNone(emails, "Emails list should not be None")
#            self.assertEqual(len(emails), 1, "Should retrieve one email successfully")
#            self.assertEqual(emails[0]['id'], 'id2')
#            mock_logging.error.assert_any_call("SSL Error fetching email details for ID id1: SSL get error for id1. Skipping this email.")

#    @patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file')
#    @patch('google.oauth2.credentials.Credentials.from_authorized_user_file')
#    @patch('googleapiclient.discovery.build')
#    @patch('gmail_chatbot.email_gmail_api.GMAIL_TOKEN_FILE', TEST_TOKEN_FILE)
#    @patch('gmail_chatbot.email_gmail_api.GMAIL_CLIENT_SECRET_FILE', TEST_CLIENT_SECRET_FILE)
#    def test_get_email_by_id_ssl_error(self, mock_gcsf_const, mock_gtf_const, mock_build, mock_creds_from_file, mock_flow_from_secrets):
#        mock_service_instance = MagicMock()
#        mock_service_instance.users().messages().get().execute.side_effect = ssl.SSLError("SSL get_by_id error")
#        mock_build.return_value = mock_service_instance
#        mock_creds_from_file.return_value = MagicMock(spec=Credentials, valid=True, expired=False)
#
#        # InstalledAppFlow is now patched at the method level by mock_flow_from_secrets
#        client = GmailAPIClient(self.mock_claude_client, self.mock_system_message)
#
#        email_data, error_msg = client.get_email_by_id("test_id")
#        self.assertIsNone(email_data)
#        self.assertIsNotNone(error_msg)
#        self.assertIn("SSL error fetching email (ID: test_id): SSL get_by_id error", error_msg)


class TestLastGmailErrorFlag(unittest.TestCase):
    def setUp(self):
        import sys
        import types
        if 'streamlit' not in sys.modules:
            st_stub = types.ModuleType('streamlit')
            class SessionState(dict):
                def __getattr__(self, item):
                    return self.get(item)

                def __setattr__(self, key, value):
                    self[key] = value

            st_stub.session_state = SessionState()
            sys.modules['streamlit'] = st_stub
        else:
            st_stub = sys.modules['streamlit']
            if not isinstance(st_stub.session_state, dict):
                st_stub.session_state = st_stub.session_state.__class__()
            else:
                st_stub.session_state = type('SessionState', (dict,), {})()
        self.st = st_stub
        import gmail_chatbot.app.core as core
        core.st = st_stub

    def test_flag_set_on_failure(self):
        from gmail_chatbot.email_main import GmailChatbotApp
        app = GmailChatbotApp.__new__(GmailChatbotApp)
        app.gmail_client = MagicMock()
        app.memory_actions_handler = MagicMock()
        error_msg = "SSL Error retrieving email"
        app.gmail_client.get_email_by_id.return_value = (None, error_msg)
        app.get_email_by_id = GmailChatbotApp.get_email_by_id.__get__(app)
        result = app.get_email_by_id("1")
        self.assertEqual(self.st.session_state.get('last_gmail_error'), error_msg)
        self.assertEqual(result, error_msg)


if __name__ == "__main__":
    unittest.main()
