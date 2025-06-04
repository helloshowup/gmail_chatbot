"""Command-line interface for the Gmail Chatbot."""

import argparse
from .app.core import GmailChatbotApp


def main(argv: list[str] | None = None) -> None:
    """Run the Gmail Chatbot application."""
    parser = argparse.ArgumentParser(description="Gmail Chatbot")
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Run without launching the Tkinter GUI.",
    )
    args = parser.parse_args(argv)

    app = GmailChatbotApp()
    if args.no_gui:
        from .gui.core import EmailChatbotGUI

        gui = EmailChatbotGUI(app.process_message)
        gui.headless_mode = True
        gui.run()
    else:
        app.run()


if __name__ == "__main__":  # pragma: no cover - manual invocation
    main()
