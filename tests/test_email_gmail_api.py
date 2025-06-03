import unittest
from unittest.mock import patch, MagicMock, mock_open, ANY # Restore ANY
import os # Restore os
import sys # Restore sys
import ssl # For ssl.SSLError
import logging # For disabling/enabling logger in tests
import json # For creating mock client_secret file
import pickle # For mocking credential loading/saving
from pathlib import Path # For type checking in mocks

# Adjust sys.path to include the project root ('showup-tools')
project_root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root_dir not in sys.path:
    sys.path.insert(0, project_root_dir)

from gmail_chatbot.email_gmail_api import GmailAPIClient
from google.oauth2.credentials import Credentials # For type hinting and creating mock creds
import google.auth.exceptions # For RefreshError

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

        # Create a dummy token file to ensure os.path.exists(token_path) is true
        # Its content doesn't matter as pickle.load will be mocked.
        # tearDown will remove this file.
        # No longer need to create TEST_TOKEN_FILE if we mock os.path.exists and open for it.

        # Path to the expected token file, relative to how email_gmail_api.py constructs it.
        # Assuming DATA_DIR in email_gmail_api.py resolves correctly during its import.
        # We'll mock interactions with this path.
        # This is a bit fragile if DATA_DIR calculation changes, but let's try.
        # For now, let's assume the test setup for TEST_CLIENT_SECRET_FILE is okay for from_client_secrets_file mock.

        self.addCleanup(google_api_logger.setLevel, original_level) # Ensure restoration

        # Import constants here, inside the test method, but before the patch context
        # if they are needed for setup outside the patch that might trigger module access.
        # However, for this specific test, they are primarily used by GmailAPIClient itself or for os.path.exists mock setup.
        # Let's import them inside the patch context to be safe, or ensure paths are constructed directly.

        with patch('pathlib.Path.mkdir') as mock_mkdir, \
             patch('os.path.exists') as mock_os_path_exists, \
             patch('builtins.open', new_callable=MagicMock) as mock_open, \
             patch('google.auth.transport.requests.Request') as mock_google_request, \
             patch('pickle.load') as mock_pickle_load, \
             patch('email_gmail_api.build') as mock_build, \
             patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file') as mock_flow_from_secrets:

            # Ensure pathlib.Path.mkdir does nothing to prevent side effects
            mock_mkdir.return_value = None

            # Configure os.path.exists mock to avoid recursion and handle the token file path
            def mock_exists_logic(path_arg):
                # This check needs to be robust based on how _authenticate forms the path.
                # It uses DATA_DIR / GMAIL_TOKEN_FILE. GMAIL_TOKEN_FILE is 'test_token.json' (TEST_TOKEN_FILE).
                # So, we expect path_arg to be a Path object.
                if isinstance(path_arg, Path) and path_arg.name == 'token.json': # Match actual GMAIL_TOKEN_FILE name
                    # print(f"DEBUG: mock_os_path_exists returning True for {path_arg}") # Temporary debug
                    return True
                # print(f"DEBUG: mock_os_path_exists returning False for {path_arg}") # Temporary debug
                return False # Default to False for other paths to avoid unexpected behavior or recursion
            mock_os_path_exists.side_effect = mock_exists_logic

            # mock_open is patched but pickle.load is also patched, so open might not be called directly by test logic for token reading.
            # If pickle.dump needs it for TEST_TOKEN_FILE, it's covered by new_callable=MagicMock.

            # Simulate successful loading of valid, non-expired credentials from token file
            mock_loaded_credentials = MagicMock(spec=Credentials)
            mock_loaded_credentials.valid = True
            # Let other attributes be default MagicMocks. The path taken should only rely on .valid.
            mock_pickle_load.return_value = mock_loaded_credentials

            # mock_flow_from_secrets is patched, its default MagicMock return is fine.

            # Mock build to raise an SSL error with an explicit errno
            mock_build.side_effect = ssl.SSLError("Simulated SSL Error during build")

            # Import the class and constants to be tested/used from within the patch context
            # to ensure we are using the potentially reloaded module where 'build' is patched.
            from email_gmail_api import GmailAPIClient, DATA_DIR, GMAIL_TOKEN_FILE, GMAIL_CLIENT_SECRET_FILE

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

    @patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file')
    @patch('google.oauth2.credentials.Credentials.from_authorized_user_file')
    @patch('googleapiclient.discovery.build')
    @patch('gmail_chatbot.email_gmail_api.GMAIL_TOKEN_FILE', TEST_TOKEN_FILE)
    @patch('gmail_chatbot.email_gmail_api.GMAIL_CLIENT_SECRET_FILE', TEST_CLIENT_SECRET_FILE)
    def test_authenticate_ssl_error_on_refresh_then_flow_fails(self, mock_gcsf_const, mock_gtf_const, mock_build, mock_creds_from_file, mock_flow_from_secrets):
        """Test SSL on refresh, then flow fails, leading to auth failure."""
        mock_credentials = MagicMock(spec=Credentials)
        mock_credentials.valid = False
        mock_credentials.expired = True
        mock_credentials.refresh_token = "fake_refresh_token"
        mock_credentials.refresh.side_effect = ssl.SSLError("Simulated SSL Error during refresh")
        mock_creds_from_file.return_value = mock_credentials

        mock_flow_instance = mock_flow_from_secrets.return_value
        mock_flow_instance.run_local_server.side_effect = ValueError("Flow aborted by test during re-auth")
        
        # If refresh fails (SSL) and subsequent flow also fails, _authenticate should raise ValueError or return None.
        # If it returns None, build(..., credentials=None) would likely fail or the service attribute would be None.
        # The ValueError from _authenticate's "Failed to obtain valid credentials" is ideal.
        # Let's assume _authenticate raises ValueError if flow fails after refresh error.
        # Based on current _authenticate, if flow fails, it raises ValueError. If refresh has SSL error, it logs and creds=None, then flow runs.
        with self.assertRaisesRegex(ValueError, "Flow aborted by test during re-auth") as cm:
            client = GmailAPIClient(
                claude_client=self.mock_claude_client, 
                system_message=self.mock_system_message
            )
        # We can also check that build was not called with None credentials if _authenticate raises before build
        mock_build.assert_not_called() # Or called with specific creds if flow somehow succeeded before this mock

    @patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file')
    @patch('google.oauth2.credentials.Credentials.from_authorized_user_file')
    @patch('googleapiclient.discovery.build')
    @patch('gmail_chatbot.email_gmail_api.GMAIL_TOKEN_FILE', TEST_TOKEN_FILE)
    @patch('gmail_chatbot.email_gmail_api.GMAIL_CLIENT_SECRET_FILE', TEST_CLIENT_SECRET_FILE)
    def test_connection_ssl_error(self, mock_gcsf_const, mock_gtf_const, mock_build, mock_creds_from_file, mock_flow_from_secrets):
        """Test test_connection handles SSL error."""
        mock_service_instance = MagicMock()
        mock_service_instance.users().getProfile().execute.side_effect = ssl.SSLError("Simulated SSL Error on getProfile")
        mock_build.return_value = mock_service_instance
        mock_creds_from_file.return_value = MagicMock(spec=Credentials, valid=True, expired=False)

        # InstalledAppFlow is now patched at the method level by mock_flow_from_secrets
        # mock_flow_from_secrets.from_client_secrets_file.return_value.run_local_server.return_value = MagicMock(spec=Credentials) # Example configuration
        client = GmailAPIClient(
            claude_client=self.mock_claude_client, 
            system_message=self.mock_system_message
        )
        result = client.test_connection()
        self.assertFalse(result['success'])
        self.assertEqual(result['error_type'], 'ssl_error')
        self.assertIn("Simulated SSL Error on getProfile", result['message'])

    @patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file')
    @patch('google.oauth2.credentials.Credentials.from_authorized_user_file')
    @patch('googleapiclient.discovery.build')
    @patch('gmail_chatbot.email_gmail_api.GMAIL_TOKEN_FILE', TEST_TOKEN_FILE)
    @patch('gmail_chatbot.email_gmail_api.GMAIL_CLIENT_SECRET_FILE', TEST_CLIENT_SECRET_FILE)
    def test_search_emails_ssl_error_on_list(self, mock_gcsf_const, mock_gtf_const, mock_build, mock_creds_from_file, mock_flow_from_secrets):
        mock_service_instance = MagicMock()
        mock_service_instance.users().messages().list().execute.side_effect = ssl.SSLError("SSL list error")
        mock_build.return_value = mock_service_instance
        mock_creds_from_file.return_value = MagicMock(spec=Credentials, valid=True, expired=False)

        # InstalledAppFlow is now patched at the method level by mock_flow_from_secrets
        client = GmailAPIClient(self.mock_claude_client, self.mock_system_message)
        
        emails, error_msg = client.search_emails("test query")
        self.assertIsNone(emails)
        self.assertIsNotNone(error_msg)
        self.assertIn("SSL error during email search (listing messages): SSL list error", error_msg)

    @patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file')
    @patch('google.oauth2.credentials.Credentials.from_authorized_user_file')
    @patch('googleapiclient.discovery.build')
    @patch('gmail_chatbot.email_gmail_api.GMAIL_TOKEN_FILE', TEST_TOKEN_FILE)
    @patch('gmail_chatbot.email_gmail_api.GMAIL_CLIENT_SECRET_FILE', TEST_CLIENT_SECRET_FILE)
    def test_search_emails_ssl_error_on_get_skips(self, mock_gcsf_const, mock_gtf_const, mock_build, mock_creds_from_file, mock_flow_from_secrets):
        mock_service_instance = MagicMock()
        mock_service_instance.users().messages().list().execute.return_value = {
            'messages': [{'id': 'id1', 'threadId': 'thread1'}, {'id': 'id2', 'threadId': 'thread2'}],
            'resultSizeEstimate': 2
        }
        
        # Mock the 'get' method on the messages resource
        mock_messages_resource = mock_service_instance.users().messages()
        mock_get_method = MagicMock()
        mock_get_method.execute.side_effect = [
            ssl.SSLError("SSL get error for id1"),
            {'id': 'id2', 'snippet': 'Test email 2', 'payload': {'headers': [{'name': 'Subject', 'value': 'Subject 2'}]}}
        ]
        mock_messages_resource.get = mock_get_method # Attach the mock 'get' to the messages resource
        
        mock_build.return_value = mock_service_instance
        mock_creds_from_file.return_value = MagicMock(spec=Credentials, valid=True, expired=False)

        # InstalledAppFlow is now patched at the method level by mock_flow_from_secrets
        client = GmailAPIClient(self.mock_claude_client, self.mock_system_message)
        
        with patch('gmail_chatbot.email_gmail_api.logging') as mock_logging:
            emails, error_msg = client.search_emails("test query", max_results=2)
            self.assertIsNone(error_msg, "Overall search should not report an error if some emails are processed")
            self.assertIsNotNone(emails, "Emails list should not be None")
            self.assertEqual(len(emails), 1, "Should retrieve one email successfully")
            self.assertEqual(emails[0]['id'], 'id2')
            mock_logging.error.assert_any_call("SSL Error fetching email details for ID id1: SSL get error for id1. Skipping this email.")

    @patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file')
    @patch('google.oauth2.credentials.Credentials.from_authorized_user_file')
    @patch('googleapiclient.discovery.build')
    @patch('gmail_chatbot.email_gmail_api.GMAIL_TOKEN_FILE', TEST_TOKEN_FILE)
    @patch('gmail_chatbot.email_gmail_api.GMAIL_CLIENT_SECRET_FILE', TEST_CLIENT_SECRET_FILE)
    def test_get_email_by_id_ssl_error(self, mock_gcsf_const, mock_gtf_const, mock_build, mock_creds_from_file, mock_flow_from_secrets):
        mock_service_instance = MagicMock()
        mock_service_instance.users().messages().get().execute.side_effect = ssl.SSLError("SSL get_by_id error")
        mock_build.return_value = mock_service_instance
        mock_creds_from_file.return_value = MagicMock(spec=Credentials, valid=True, expired=False)

        # InstalledAppFlow is now patched at the method level by mock_flow_from_secrets
        client = GmailAPIClient(self.mock_claude_client, self.mock_system_message)

        email_data, error_msg = client.get_email_by_id("test_id")
        self.assertIsNone(email_data)
        self.assertIsNotNone(error_msg)
        self.assertIn("SSL error fetching email (ID: test_id): SSL get_by_id error", error_msg)

if __name__ == '__main__':
    unittest.main()
