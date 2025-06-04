from unittest.mock import MagicMock, patch

from gmail_chatbot.preference_detector import PreferenceDetector


@patch("gmail_chatbot.preference_detector.classify_query_type")
def test_preference_detector_stores_preference(mock_classify):
    """PreferenceDetector should store preferences via EnhancedMemoryStore."""
    mock_classify.return_value = ("preference_update", 0.9, {})
    memory_store = MagicMock()
    detector = PreferenceDetector(memory_store)

    detected, feedback = detector.process_message(
        "ShowUp or showup.courses is my brand"
    )

    assert detected
    memory_store.remember_user_preference.assert_called_once_with(
        "ShowUp or showup.courses is my brand", label="general_preference"
    )
    assert "Noted" in feedback
