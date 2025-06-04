"""Backward compatibility wrapper for the GUI components."""

from gmail_chatbot.gui.core import (
    EmailChatbotGUI,
    GUI_AVAILABLE,
    can_initialize_gui,
)

__all__ = ["EmailChatbotGUI", "GUI_AVAILABLE", "can_initialize_gui"]
