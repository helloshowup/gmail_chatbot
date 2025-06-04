import logging
import streamlit as st
import sys
import os
import traceback

import io
import time
import json
import uuid
from pathlib import Path
from gmail_chatbot.agentic_planner import generate_plan
from gmail_chatbot.agentic_executor import (
    execute_step,
    summarize_and_log_agentic_results,  # Added for agentic execution
    handle_step_limit_reached,
)
from gmail_chatbot.email_config import CLAUDE_API_KEY_ENV, load_env

# Module-level logger
logger = logging.getLogger(__name__)


# --- Global Exception Hook for Debugging ---
def log_exception_to_file(exc_type, exc_value, exc_traceback):
    error_log_file = Path(__file__).resolve().parent / "streamlit_crash_report.txt"
    with open(error_log_file, "a") as f:
        f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        # Format traceback
        string_buffer = io.StringIO()
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=string_buffer)
        f.write(string_buffer.getvalue())
        f.write("-----------------------------------------------------\n")
    # Also print to stderr as originally intended by Python
    traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)

sys.excepthook = log_exception_to_file
# --- End Global Exception Hook ---

# Page config
st.set_page_config(page_title="Gmail Chatbot", layout="wide")

# from email_main import GmailChatbotApp # MOVED

st.title("✉️ Gmail Claude Chatbot Assistant")

# --- Agentic Mode Initialization & Controls ---
# Ensure all agentic mode related keys are initialized first
default_agentic_state_values = {
    "current_step_index": 0,
    "executed_call_count": 0,
    "accumulated_results": {},
    "error_messages": []
}
if "agentic_mode_enabled" not in st.session_state:
    st.session_state.agentic_mode_enabled = False # This will be the source for the toggle's default
if "agentic_step_limit" not in st.session_state:
    st.session_state.agentic_step_limit = 10 # Source for number_input's default
if "agentic_plan" not in st.session_state:
    st.session_state.agentic_plan = None
if "agentic_state" not in st.session_state:
    st.session_state.agentic_state = default_agentic_state_values.copy()
if "pending_confirmation" not in st.session_state:
    st.session_state.pending_confirmation = None

# Sidebar controls
st.sidebar.header("🤖 Agentic Mode Settings")

# Store previous mode to detect changes for reset logic
_previous_agentic_mode_status = st.session_state.agentic_mode_enabled

st.sidebar.toggle( # This widget will now directly control st.session_state.agentic_mode_enabled
    "Enable Agentic Mode",
    key="agentic_mode_enabled", # Binds widget to this session state key
    help="Allow the chatbot to autonomously execute a plan with multiple steps."
)

# If agentic mode was just turned OFF, reset plan and associated state.
if _previous_agentic_mode_status and not st.session_state.agentic_mode_enabled:
    st.session_state.agentic_plan = None
    st.session_state.agentic_state = default_agentic_state_values.copy()
    # Optional: st.rerun() if other UI elements depend critically on this reset immediately.

if st.session_state.agentic_mode_enabled:
    st.sidebar.number_input( # This widget directly controls st.session_state.agentic_step_limit
        "Max Autonomous Steps",
        min_value=1,
        max_value=50, # Sensible default max
        key="agentic_step_limit", # Binds widget to this session state key
        step=1,
        help="Maximum number of API/tool calls the agent can make autonomously in one go."
    )
# --- End Agentic Mode Initialization & Controls ---


def run_agentic_plan() -> None:
    """Execute the current agentic plan sequentially with progress feedback."""
    plan = st.session_state.get("agentic_plan")
    if not plan:
        return
    if not isinstance(plan, list):
        logger.info("Parsing error: agentic_plan is not a list")
        return

    agentic_state = st.session_state.get("agentic_state", default_agentic_state_values.copy())
    step_limit = st.session_state.get("agentic_step_limit", 10)

    progress_bar = st.progress(
        agentic_state.get("current_step_index", 0) / max(len(plan), 1)
    )

    while (
        agentic_state.get("current_step_index", 0) < len(plan)
        and agentic_state.get("executed_call_count", 0) < step_limit
    ):
        idx = agentic_state.get("current_step_index", 0)
        step_details = plan[idx]
        if not isinstance(step_details, dict):
            logger.info("Parsing error: step %s is not a dict", idx)
            break
        logger.info(
            "Starting step %s (%s)",
            step_details.get("step_id", "N/A"),
            step_details.get("action_type"),
        )
        with st.spinner(f"Executing: {step_details.get('description', 'Working...')}"):
            try:
                execution_result = execute_step(step_details, agentic_state)
            except Exception as e:  # pragma: no cover - defensive
                st.exception(e)
                st.error(f"An unexpected error occurred during step execution: {e}")
                st.session_state.agentic_plan = None
                st.session_state.agentic_state = default_agentic_state_values.copy()
                return

        agentic_state = execution_result.get("updated_agentic_state", agentic_state)
        agentic_state["executed_call_count"] = agentic_state.get("executed_call_count", 0) + 1

        if execution_result.get("status") == "failure":
            error_msg = (
                f"Step {idx + 1} ('{step_details.get('step_id', 'Unnamed')}') failed:"
                f" {execution_result.get('message', 'Unknown error')}"
            )
            st.error(error_msg)
            agentic_state.setdefault("error_messages", []).append(error_msg)
            summarize_and_log_agentic_results(agentic_state, plan_completed=False)
            st.session_state.agentic_plan = None
            st.session_state.agentic_state = default_agentic_state_values.copy()
            return

        if execution_result.get("requires_user_input", False):
            st.info(
                f"Step {idx + 1} requires user input: {execution_result.get('message', '')}"
            )
            st.session_state.agentic_state = agentic_state
            progress_bar.progress((idx + 1) / len(plan))
            return

        if execution_result.get("status") == "skipped":
            st.info(execution_result.get("message", "Step skipped"))

        agentic_state["current_step_index"] = idx + 1
        st.session_state.agentic_state = agentic_state
        progress_bar.progress(agentic_state["current_step_index"] / len(plan))
        state_summary = {
            "executed_call_count": agentic_state.get("executed_call_count"),
            "current_step_index": agentic_state.get("current_step_index"),
            "result_keys": list(agentic_state.get("accumulated_results", {}).keys()),
        }
        logger.info(
            "Finished step %s (%s) summary=%s",
            step_details.get("step_id", "N/A"),
            step_details.get("action_type"),
            state_summary,
        )

    if agentic_state.get("current_step_index", 0) >= len(plan):
        summarize_and_log_agentic_results(agentic_state, plan_completed=True)
        st.success("🎉 Agentic plan fully completed!")
        st.session_state.agentic_plan = None
        st.session_state.agentic_state = default_agentic_state_values.copy()
        st.balloons()
    elif agentic_state.get("executed_call_count", 0) >= step_limit:
        user_choice = handle_step_limit_reached(agentic_state, step_limit)
        if user_choice == "continue":
            st.session_state.agentic_state = agentic_state
            st.rerun()
        elif user_choice == "stop":
            st.session_state.agentic_plan = None
            st.session_state.agentic_state = default_agentic_state_values.copy()
            st.rerun()
        else:
            st.stop()

# Initialize chat history

def initialize_chatbot() -> bool:
    """Attempts to initialize the chatbot application, returns True on success, False on failure."""
    st.session_state["initialization_steps"] = [] # Initialize early, done before any potential failure point

    env_path = Path(__file__).resolve().parent / ".env"
    load_env()
    if env_path.exists():
        st.session_state["initialization_steps"].append(
            str(f"✓ .env file loaded from {env_path}")
        )
    else:
        st.session_state["initialization_steps"].append(
            str(
                f"⚠️ .env file not found at {env_path}. Some features might not work."
            )
        )
        # This might not be critical enough to stop, depending on what's in .env, but API key check below is.

    # Check for Anthropic API key before attempting to initialize
    if not os.environ.get(CLAUDE_API_KEY_ENV):
        error_msg = str(f"✗ Missing {CLAUDE_API_KEY_ENV} environment variable. Please set it in your .env file or environment.")
        st.session_state["initialization_steps"].append(error_msg)
        st.error(error_msg)
        st.warning("The application cannot start without the Anthropic API key. Please set it and refresh.")
        st.session_state["bot_initialized_successfully"] = False
        st.stop() # Critical failure, stop execution
        return False # Should not be reached due to st.stop()
    else:
        st.session_state["initialization_steps"].append(str(f"✓ {CLAUDE_API_KEY_ENV} found."))

    st.info("Initializing chatbot... This might take a moment on the first run.")
    with st.spinner("Please wait: Setting up AI model and connecting to services..."):
        try:
            st.session_state["bot_initialized_successfully"] = True # Assume success, set to False on any failure

            st.session_state["initialization_steps"].append(str("Attempting to import GmailChatbotApp..."))
            print("DEBUG: chat_app_st.py - BEFORE GmailChatbotApp import", file=sys.stderr, flush=True)
            try:
                from gmail_chatbot.email_main import GmailChatbotApp
                print("DEBUG: chat_app_st.py - Import statement for GmailChatbotApp COMPLETED.", file=sys.stderr, flush=True)
                if not ('GmailChatbotApp' in locals() and isinstance(GmailChatbotApp, type)):
                    critical_msg = "CRITICAL_DEBUG: chat_app_st.py - GmailChatbotApp import issue. Not a class after import."
                    print(critical_msg, file=sys.stderr)
                    raise RuntimeError(critical_msg)
                st.session_state["initialization_steps"].append(str("✓ GmailChatbotApp imported successfully"))
                st.session_state["gmail_chatbot_app_imported"] = True
            except ImportError as import_err:
                print(f"CRITICAL_DEBUG: chat_app_st.py - FAILED to import GmailChatbotApp: {import_err}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                st.session_state["initialization_steps"].append(str(f"✗ FAILED to import GmailChatbotApp: {import_err}"))
                st.session_state["bot_initialized_successfully"] = False
                return False # Critical import failure
            
            autonomous_task_counter_key = "autonomous_task_counter"
            if autonomous_task_counter_key not in st.session_state:
                st.session_state[autonomous_task_counter_key] = 0
            st.session_state["initialization_steps"].append(str("✓ Autonomous task counter initialized"))

            st.session_state["initialization_steps"].append(str("Attempting to create GmailChatbotApp instance..."))
            print("DEBUG: chat_app_st.py - BEFORE GmailChatbotApp instantiation", file=sys.stderr, flush=True)
            st.session_state.bot = GmailChatbotApp(autonomous_counter_ref=st.session_state)
            print("DEBUG: chat_app_st.py - AFTER GmailChatbotApp instantiation", file=sys.stderr, flush=True)
            st.session_state["initialization_steps"].append(str("✓ GmailChatbotApp instance created"))

            # --- Critical Component Checks --- 
            st.session_state["initialization_steps"].append(str("Verifying critical bot components..."))

            print("DEBUG: chat_app_st.py - BEFORE Gmail client check", file=sys.stderr, flush=True)
            # 1. Gmail Client (Service Object and API Connection)
            if hasattr(st.session_state.bot, 'gmail_service') and st.session_state.bot.gmail_service is not None:
                st.session_state["initialization_steps"].append(str("✓ Gmail client object loaded (gmail_service found)."))
                # Now test the connection (this method should ideally add its own detailed step to initialization_steps)
                if hasattr(st.session_state.bot, 'test_gmail_api_connection') and callable(getattr(st.session_state.bot, 'test_gmail_api_connection')):
                    # The test_gmail_api_connection method in email_main.py should append its own status to st.session_state.bot.initialization_diagnostics
                    # which will then be copied or used here. For now, we assume it returns bool and we add a generic message.
                    gmail_api_ok, msg = st.session_state.bot.test_gmail_api_connection() # Expecting (bool, str) from modified version
                    st.session_state["initialization_steps"].append(str(msg)) # Add message from test_gmail_api_connection
                    if not gmail_api_ok:
                        st.session_state["bot_initialized_successfully"] = False
                else:
                    st.session_state["initialization_steps"].append(str("⚠️ Gmail API connection test method not found on bot object. Cannot verify connection."))
                    # Depending on strictness, this could be a failure: st.session_state["bot_initialized_successfully"] = False
            else:
                st.session_state["initialization_steps"].append(str("✗ Gmail client (gmail_service) failed to load or is None."))
                st.session_state["bot_initialized_successfully"] = False
            print("DEBUG: chat_app_st.py - AFTER Gmail client check", file=sys.stderr, flush=True)

            print("DEBUG: chat_app_st.py - BEFORE Vector search check", file=sys.stderr, flush=True)
            # 2. Vector Search (Embedding Model + FAISS)
            if hasattr(st.session_state.bot, 'vector_search_available'):
                if st.session_state.bot.vector_search_available:
                    st.session_state["initialization_steps"].append(str("✓ Vector search loaded and available."))
                else:
                    error_detail = "Vector search component reported as unavailable."
                    if hasattr(st.session_state.bot, 'get_vector_search_error_message') and callable(
                        st.session_state.bot.get_vector_search_error_message
                    ):
                        msg = st.session_state.bot.get_vector_search_error_message()
                        if msg:
                            error_detail = str(msg)  # Ensure string
                    st.session_state["initialization_steps"].append(str(f"✗ Vector search failed: {error_detail}"))
                    # Vector search failure is non-critical for degraded mode.
                    # Store warning for UI display.
                    st.session_state.vector_search_ui_warning = str(f"⚠️ Vector Search Unavailable: {error_detail}. The chatbot will operate in a degraded mode. Semantic search and some advanced features may be disabled.") 
            else:
                st.session_state["initialization_steps"].append(str("✗ Vector search status unknown (attribute 'vector_search_available' missing on bot object)."))
                st.session_state["bot_initialized_successfully"] = False
            print("DEBUG: chat_app_st.py - AFTER Vector search check", file=sys.stderr, flush=True)

            print("DEBUG: chat_app_st.py - BEFORE Email memory store check", file=sys.stderr, flush=True)
            # 3. Email Memory Store
            if hasattr(st.session_state.bot, 'email_memory') and st.session_state.bot.email_memory is not None:
                st.session_state["initialization_steps"].append(str("✓ Email memory store available."))
            else:
                st.session_state["initialization_steps"].append(str("✗ Email memory store not available or is None."))
                st.session_state["bot_initialized_successfully"] = False
            print("DEBUG: chat_app_st.py - AFTER Email memory store check", file=sys.stderr, flush=True)

            print("DEBUG: chat_app_st.py - BEFORE Claude client check", file=sys.stderr, flush=True)
            # Check other non-critical components if necessary (original loop can be adapted for this)
            # For now, focusing on the three specified as critical.
            # Example: Claude client check (often critical too)
            if hasattr(st.session_state.bot, 'claude_client') and st.session_state.bot.claude_client is not None:
                st.session_state["initialization_steps"].append(str("✓ Claude API client loaded."))
            else:
                st.session_state["initialization_steps"].append(str("✗ Claude API client failed to load."))
                st.session_state["bot_initialized_successfully"] = False # Claude is usually critical
            print("DEBUG: chat_app_st.py - AFTER Claude client check", file=sys.stderr, flush=True)

            if not st.session_state["bot_initialized_successfully"]:
                print(f"CRITICAL_DEBUG: chat_app_st.py - Initialization failed. Final steps: {st.session_state['initialization_steps']}", file=sys.stderr)
                return False # One of the critical checks failed

            st.session_state["initialization_steps"].append(str("✓ All critical bot components verified successfully."))

        except ImportError as import_err: # Handle import errors specifically
            print(f"CRITICAL_DEBUG: chat_app_st.py - Initialization failed due to ImportError: {import_err}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            st.session_state["initialization_steps"].append(str(f"✗ CRITICAL: Failed to import a required module: {import_err}"))
            st.session_state["bot_initialized_successfully"] = False
            # No need to return False here if already set, but good for clarity if this was the only error point.

        except Exception as e:
            st.error(f"An unexpected error occurred during chatbot initialization: {e}")
            print(f"CRITICAL_DEBUG: chat_app_st.py - Unexpected error during initialization: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            st.session_state["initialization_steps"].append(str(f"✗ UNEXPECTED ERROR during initialization: {e}"))
            st.session_state["bot_initialized_successfully"] = False
            # No need to return False here if already set.
        
    # Final return based on the flag, which aggregates all checks
    if not st.session_state.get("bot_initialized_successfully", False):
        return False # Return False if any step set it to False
    
    return True # All good if we reached here and flag is still True

# --- Main Application Flow ---
# Attempt initialization if not already successfully initialized.
if not st.session_state.get("bot_initialized_successfully", False):
    initialize_chatbot() # This function will populate 'initialization_steps' and set 'bot_initialized_successfully'.

# Display initialization diagnostics regardless of outcome, using an expander.
if "initialization_steps" in st.session_state and st.session_state.initialization_steps:
    expander_opened_by_default = not st.session_state.get("bot_initialized_successfully", False)
    with st.expander("Initialization Progress Details", expanded=expander_opened_by_default):
        for step_message in st.session_state["initialization_steps"]:
            msg_str = str(step_message)  # Ensure it's a string
            if msg_str.startswith("✓") or "success" in msg_str.lower() or "🎉" in msg_str:
                st.success(msg_str)
            elif msg_str.startswith("✗") or "fail" in msg_str.lower() or "error" in msg_str.lower():
                st.error(msg_str)
            elif msg_str.startswith("⚠️") or "warn" in msg_str.lower():
                st.warning(msg_str)
            else:
                st.info(msg_str)

# Guard for Chat Interface: Only proceed if bot is successfully initialized.
if not st.session_state.get("bot_initialized_successfully", False):
    st.error("Chatbot is not ready. Please review the initialization messages above or check the application logs.")
    st.warning("Ensure API keys are correct and services are reachable. You may need to refresh the page to retry initialization.")
    st.stop()  # Stop rendering the rest of the page, including chat input

# If we reach here, bot is initialized successfully.
# Optionally, a subtle confirmation or just proceed to chat interface.
# st.success("Chatbot ready!") # This can be a bit noisy on every interaction.

# Display vector search warning if set
if "vector_search_ui_warning" in st.session_state and st.session_state.vector_search_ui_warning:
    st.warning(st.session_state.vector_search_ui_warning)

if st.session_state.get("last_gmail_error"):
    st.error(st.session_state.last_gmail_error)
    st.session_state.last_gmail_error = ""

# --- Chat History Display ---chat messages from history on app rerun
if "bot" in st.session_state and hasattr(st.session_state.bot, "chat_history"):
    for message in st.session_state.bot.chat_history: # Use bot's history
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

# Accept user input
if prompt := st.chat_input("Ask me about your inbox:"):
    # Display user message and add to history immediately
    with st.chat_message("user"):
        st.markdown(prompt)
    
    if st.session_state.get("bot_initialized_successfully") and "bot" in st.session_state:
        if not hasattr(st.session_state.bot, "chat_history") or not isinstance(st.session_state.bot.chat_history, list):
            st.session_state.bot.chat_history = [] # Initialize if missing
        st.session_state.bot.chat_history.append({"role": "user", "content": prompt})
    else:
        # If bot not initialized, display error and stop further processing for this input
        st.error("Chatbot is not initialized. Cannot process messages.")
        st.stop() # Stop current script run


    # Determine how to handle the prompt based on agentic mode
    if st.session_state.get("agentic_mode_enabled"):
        if not st.session_state.get("agentic_plan"):
            with st.spinner("Bot is thinking..."):
                spinner_placeholder = st.empty()
                spinner_placeholder.markdown("### \u23f3 Bot is thinking...")
                plan = generate_plan(prompt, st.session_state)
                spinner_placeholder.empty()
            if plan is None:
                assistant_reply = st.session_state.bot.process_message(prompt)
                with st.chat_message("assistant"):
                    st.markdown(assistant_reply)
                st.session_state.bot.chat_history.append({"role": "assistant", "content": assistant_reply})
            else:
                st.session_state.agentic_plan = plan
                st.session_state.agentic_state = default_agentic_state_values.copy()
                plan_str = json.dumps(plan, indent=2)
                with st.chat_message("assistant"):
                    st.markdown("**Generated Plan:**")
                    st.json(plan)
                st.session_state.bot.chat_history.append({"role": "assistant", "content": f"Generated Plan:\n{plan_str}"})
        if st.session_state.get("agentic_plan"):
            run_agentic_plan()
    else:
        with st.spinner("Bot is thinking..."):
            spinner_placeholder = st.empty()
            spinner_placeholder.markdown("### \u23f3 Bot is thinking...")
            assistant_reply = st.session_state.bot.process_message(prompt)
            spinner_placeholder.empty()
        with st.chat_message("assistant"):
            st.markdown(assistant_reply)

st.sidebar.title("Controls")
if "batch_mode" not in st.session_state:
    st.session_state.batch_mode = False  # Initialize if not present
st.session_state.batch_mode = st.sidebar.checkbox(
    "Batch Mode", value=st.session_state.batch_mode, key="batch_mode_checkbox"
)

if st.sidebar.button("Show Notebook Summary"):
    if st.session_state.get("bot"):
        summary = st.session_state.bot.get_notebook_overview(str(uuid.uuid4()))
        st.sidebar.info(summary)
    else:
        st.sidebar.warning("Bot not initialized.")

log_file = st.sidebar.file_uploader(
    "Upload log file for review", type="txt", key="log_uploader"
)
if log_file:
    st.sidebar.subheader("Log File Content")
    try:
        log_content = log_file.read().decode("utf-8")
        st.sidebar.code(log_content, language="text")
    except Exception as e:
        st.sidebar.error(f"Error reading log file: {e}")

st.sidebar.markdown("---")
st.sidebar.caption("Powered by Claude + Gmail API")
