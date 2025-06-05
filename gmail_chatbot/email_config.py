#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
from pathlib import Path
from datetime import date

# Import the warm functional system message
# This is imported via a function to avoid circular imports
def get_warm_functional_system_message():
    from .prompt_templates import WARM_FUNCTIONAL_SYSTEM_MESSAGE
    return WARM_FUNCTIONAL_SYSTEM_MESSAGE

# API configuration
CLAUDE_API_KEY_ENV = "ANTHROPIC_API_KEY"  # Using the existing Anthropic API key in the .env file
GMAIL_CLIENT_SECRET_FILE = "client_secret.json"
GMAIL_TOKEN_FILE = "token.json"

# Gmail API scopes
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# File paths
BASE_DIR = Path(__file__).resolve().parent
# The project root is one level above this module's package
PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
GLOBAL_LOGS_DIR = PROJECT_DIR / "logs"
API_LOGS_DIR = GLOBAL_LOGS_DIR / "gmail_chatbot_api"

# Create directories if they don't exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(GLOBAL_LOGS_DIR, exist_ok=True)
os.makedirs(API_LOGS_DIR, exist_ok=True)

# Environment handling
def load_env() -> None:
    """Load environment variables from a .env file in the project root."""
    try:
        import dotenv
    except ImportError:  # pragma: no cover - optional dependency
        return

    env_path = PROJECT_DIR / ".env"
    if env_path.exists():
        dotenv.load_dotenv(env_path)
    else:
        logging.warning(f"Environment file not found at {env_path}")

# Claude API configuration
CLAUDE_DEFAULT_MODEL = "claude-3-7-sonnet-20250219"
CLAUDE_PREP_MODEL_ENV = "CLAUDE_PREP_MODEL"
CLAUDE_PREP_MODEL = os.getenv(
    CLAUDE_PREP_MODEL_ENV, "claude-3-haiku-20240307"
)
CLAUDE_TRIAGE_MODEL_ENV = "CLAUDE_TRIAGE_MODEL"
CLAUDE_TRIAGE_MODEL = os.getenv(
    CLAUDE_TRIAGE_MODEL_ENV, "claude-3-haiku-20240307"
)
CLAUDE_MAX_TOKENS = 4096

# UI Configuration
UI_TITLE = "Gmail Chatbot Assistant"
UI_WIDTH = 900
UI_HEIGHT = 700
UI_THEME_COLOR = "#4285F4"  # Google blue

# Email processing configuration
MAX_EMAILS_PER_SEARCH = 10
EMAIL_DISPLAY_FORMAT = "simple"  # Options: "simple", "detailed", "raw"

# Token optimization settings
MAX_EMAIL_BODY_CHARS = 1500  # Limit email bodies to reduce token usage
STORE_FULL_EMAIL_BODIES = True  # Store full versions locally for follow-up queries

# Default system message for Claude
def get_default_system_message():
    """Get the default system message for Claude, combining personal context with warm tone.
    
    Returns:
        Complete system message with context and tone guidance
    """
    current_date_str = date.today().strftime("%d %B %Y") # e.g., "02 June 2025"
    
    new_personal_context = f"""
You are a trusted inbox assistant for Bryce Hepburn. You are also helping him pretend that he took over from himself as of 1 June 2025. The date today is {current_date_str}. You keep a local notebook of previous email content—summaries, snippets, and keywords from important messages. You can:

Refer to notes you've taken about Bryce Hepburn (like his role, clients, and email patterns).
Search your notebook first, then search the inbox directly (with permission).
Offer helpful suggestions or ask clarifying questions if a request is ambiguous.

You do not have internet access and should never claim to "look things up online BUT you can look things up on the vector database if the words search or look up is asked or used. "
"""
    
    # Import the warm functional tone
    warm_tone = get_warm_functional_system_message()
    
    # Email search formatting instructions
    email_search_instructions = """--- IMPORTANT EMAIL SEARCH FORMATTING INSTRUCTIONS ---
When searching for emails, ALWAYS format your Gmail search query using clear Gmail search operators. 

For example, when asked to find emails:
1. ALWAYS put the actual Gmail search query in backticks like `from:example@gmail.com after:2023/01/01`
2. Use proper Gmail search operators: from:, to:, subject:, after:, before:, has:attachment
3. Format dates as YYYY/MM/DD
4. DO NOT include any narrative text or explanation within the backticks
5. Place the search query in backticks BEFORE providing any explanations or details

Examples:
- For "emails from John today": `from:john after:YYYY/MM/DD before:YYYY/MM/DD`
- For "recent invoices": `subject:(invoice OR bill OR payment) after:YYYY/MM/DD`

This proper formatting is CRITICAL for the email search to work correctly.
"""
    
    # Combine personal context with warm tone guidance and search formatting instructions
    return f"{new_personal_context}\n\n{email_search_instructions}\n\n{warm_tone}"

# Create the system message
DEFAULT_SYSTEM_MESSAGE = get_default_system_message()
