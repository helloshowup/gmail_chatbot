#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
import unittest

# Add project root to path for imports
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from gmail_chatbot import api_logging


class TestLogGmailResponse(unittest.TestCase):
    """Tests for the log_gmail_response function."""

    def test_returns_path_from_log_api_interaction(self):
        """Verify return path from log_api_interaction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(api_logging, "API_LOGS_DIR", Path(tmpdir)):
                with patch.object(
                    api_logging,
                    "ensure_log_directory_exists",
                ) as mock_ensure_dir, patch.object(
                    api_logging,
                    "log_api_interaction",
                    return_value="test_path",
                ) as mock_log_interaction:
                    result = api_logging.log_gmail_response(
                        "request.json",
                        1,
                        [{"id": "1", "body": "test body"}]
                    )

                    self.assertEqual(result, "test_path")
                    mock_log_interaction.assert_called_once()


if __name__ == "__main__":
    unittest.main()
