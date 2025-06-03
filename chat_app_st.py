import streamlit as st
import sys
import os
import traceback

# --- Add package parent to sys.path ---
# __file__ is c:\Users\User\Documents\showup-v4\showup-tools\gmail_chatbot\chat_app_st.py
# package_parent_dir (containing 'gmail_chatbot' package) should be c:\Users\User\Documents\showup-v4\showup-tools
package_parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if package_parent_dir not in sys.path:
    sys.path.insert(0, package_parent_dir)
    print(f"DEBUG: chat_app_st.py - Added package parent dir to sys.path: {package_parent_dir}", file=sys.stderr)
else:
    print(f"DEBUG: chat_app_st.py - Package parent dir already in sys.path: {package_parent_dir}", file=sys.stderr)
# print(f"DEBUG: chat_app_st.py - Current sys.path: {sys.path}", file=sys.stderr) # Optional: very verbose
# --- End sys.path modification ---

import io
import time
from pathlib import Path
import dotenv
from agentic_planner import generate_plan
from agentic_executor import execute_step, summarize_and_log_agentic_results # Added for agentic execution

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
from email_config import CLAUDE_API_KEY_ENV # Assuming this is accessible
import time
from pathlib import Path
import dotenv

st.title("✉️ Gmail Claude Chatbot Assistant")

# --- Agentic Mode Initialization & Controls ---
# Ensure all agentic mode related keys are initialized first
default_agentic_state_values = {
    "current_step_index": 0,
    "executed_call_count": 0,
    "accumulated_results": [],
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

# Initialize chat history

def initialize_chatbot() -> bool:
    """Attempts to initialize the chatbot application, returns True on success, False on failure."""
    # Load .env file before checking for the API key
    dotenv_path = Path(__file__).resolve().parent / ".env"
    if dotenv_path.exists():
        dotenv.load_dotenv(dotenv_path)
        # print(f"DEBUG: Loaded .env from {dotenv_path}", file=sys.stderr)
    # else:
        # print(f"DEBUG: .env file not found at {dotenv_path}", file=sys.stderr)

    # Check for Anthropic API key before attempting to initialize
    if not os.environ.get(CLAUDE_API_KEY_ENV):
        st.error(f"Missing {CLAUDE_API_KEY_ENV} environment variable. Please set it in your .env file or environment.")
        st.warning("The application cannot start without the API key. Please set it and refresh.")
        st.session_state["bot_initialized_successfully"] = False
        st.stop() # Critical failure, stop execution
        return False # Should not be reached due to st.stop()

    st.info("Initializing chatbot... This might take a moment on the first run.")
    with st.spinner("Please wait: Setting up AI model and connecting to services..."):
        try:
            st.session_state["initialization_steps"] = [] # Initialize early
            st.session_state["initialization_steps"].append(str("Attempting to import GmailChatbotApp..."))
            print("DEBUG: chat_app_st.py - BEFORE GmailChatbotApp import", file=sys.stderr)
            print(f"DEBUG: chat_app_st.py - sys.path JUST BEFORE IMPORT: {sys.path}", file=sys.stderr)
            try:
                from email_main import GmailChatbotApp # Deferred import
                print("DEBUG: chat_app_st.py - Import statement for GmailChatbotApp COMPLETED.", file=sys.stderr)
                if not ('GmailChatbotApp' in locals() and isinstance(GmailChatbotApp, type)):
                    print(f"CRITICAL_DEBUG: chat_app_st.py - GmailChatbotApp import issue. Type: {type(GmailChatbotApp) if 'GmailChatbotApp' in locals() else 'Not in locals'}", file=sys.stderr)
                    raise RuntimeError("GmailChatbotApp not imported as a class.")
                st.session_state["initialization_steps"].append(str("✓ GmailChatbotApp imported successfully"))
                st.session_state["gmail_chatbot_app_imported"] = True
            except ImportError as import_err:
                print(f"CRITICAL_DEBUG: chat_app_st.py - FAILED to import GmailChatbotApp: {import_err}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                st.session_state["initialization_steps"].append(str(f"✗ FAILED to import GmailChatbotApp: {import_err}"))
                raise
            
            autonomous_task_counter_key = "autonomous_task_counter"
            if autonomous_task_counter_key not in st.session_state:
                st.session_state[autonomous_task_counter_key] = 0
            st.session_state["initialization_steps"].append(str("✓ Autonomous task counter initialized"))

            st.session_state["initialization_steps"].append(str("Attempting to create GmailChatbotApp instance..."))
            # Pass st.session_state itself as the mutable mapping for the counter
            st.session_state.bot = GmailChatbotApp(autonomous_counter_ref=st.session_state)
            st.session_state["initialization_steps"].append("✓ GmailChatbotApp instance created")

            st.session_state["initialization_steps"].append(str("Attempting to test Gmail API connection..."))
            if hasattr(st.session_state.bot, 'test_gmail_api_connection') and callable(getattr(st.session_state.bot, 'test_gmail_api_connection')):
                gmail_api_ok = st.session_state.bot.test_gmail_api_connection()
                if gmail_api_ok:
                    st.session_state["initialization_steps"].append(str("✓ Gmail API connection successful."))
                else:
                    st.session_state["initialization_steps"].append(str("✗ Gmail API connection FAILED. Check logs and .env credentials."))
                    # This is a critical failure for many operations, ensure bot_initialized_successfully reflects this.
                    # We will let the component check below also catch gmail_service if it's None due to this.
            else:
                st.session_state["initialization_steps"].append(str("⚠️ Gmail API connection test method not found on bot object."))

            st.session_state["initialization_steps"].append(str("Verifying bot components..."))
            
            required_components = [
                ("chat_history", "Chat history"), ("claude_client", "Claude API client"),
                ("gmail_service", "Gmail service"), ("vector_search_available", "Vector search status"),
                ("email_memory", "Email memory"), ("enhanced_memory_store", "Enhanced memory store"),
                ("preference_detector", "Preference detector"), ("memory_actions_handler", "Memory actions handler"),
                ("ml_classifier", "ML classifier")
            ]
            missing_components_details = []
            
            # Print all attributes of the bot instance for debugging
            print(f"DEBUG chat_app_st.py: Bot instance before component check loop: {st.session_state.bot}", file=sys.stderr)
            try:
                print(f"DEBUG chat_app_st.py: Attributes on bot instance (dir(bot)): {dir(st.session_state.bot)}", file=sys.stderr)
            except Exception as e_dir:
                print(f"DEBUG chat_app_st.py: Error calling dir(st.session_state.bot): {e_dir}", file=sys.stderr)

            for attr_name, desc in required_components:
                print(f"DEBUG chat_app_st.py: Checking component '{desc}' (attribute '{attr_name}')", file=sys.stderr)
                
                has_attr = hasattr(st.session_state.bot, attr_name)
                print(f"DEBUG chat_app_st.py: hasattr(bot, '{attr_name}') -> {has_attr}", file=sys.stderr)
                
                attr_value = None # Default to None
                is_missing = True # Assume missing initially

                if has_attr:
                    try:
                        attr_value = getattr(st.session_state.bot, attr_name)
                        # Check if the attribute value itself implies it's "not set" (e.g., None or False for a boolean flag)
                        if attr_value is not None: # For most objects, None means not set. For booleans, False can mean not ready.
                            if isinstance(attr_value, bool):
                                is_missing = not attr_value # If it's a bool, missing if False
                            else:
                                is_missing = False # If it's a non-None object, it's present
                        else: # attr_value is None
                            is_missing = True 
                        print(f"DEBUG chat_app_st.py: getattr(bot, '{attr_name}') -> Value: {attr_value}, Type: {type(attr_value)}, Bool_eval: {bool(attr_value)}, Considered_Missing: {is_missing}", file=sys.stderr)
                    except Exception as e_getattr:
                        print(f"DEBUG chat_app_st.py: EXCEPTION during getattr(bot, '{attr_name}'): {e_getattr}", file=sys.stderr)
                        is_missing = True # Treat as missing if getattr fails
                else: # hasattr was false
                    is_missing = True
                    print(f"DEBUG chat_app_st.py: Attribute '{attr_name}' not found by hasattr.", file=sys.stderr)
                
                if is_missing:
                    missing_components_details.append(desc)
                    print(f"DEBUG chat_app_st.py: ---> Component '{desc}' (attribute '{attr_name}') marked as MISSING.", file=sys.stderr)

            if missing_components_details:
                error_message = f"Bot initialized but missing critical components: {', '.join(missing_components_details)}"
                st.session_state["initialization_steps"].append(f"✗ {error_message}")
                raise RuntimeError(error_message)
            else:
                st.session_state["initialization_steps"].append("✓ All critical bot components verified.")

            st.session_state["bot_initialized_successfully"] = True
            st.session_state["initialization_steps"].append("🎉 Chatbot initialization successful!")
            print("DEBUG: chat_app_st.py - Bot initialized successfully and marked in session state.", file=sys.stderr)
            return True

        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            # Ensure the exception itself is added as a step
            st.session_state["initialization_steps"].append(str(f"✗ EXCEPTION during initialization: {e}"))
            # Errors will be displayed by the main app flow using the initialization_steps
            st.session_state["bot_initialized_successfully"] = False
            # No direct st.error/warning here, as it will be handled by the caller based on initialization_steps
            return False

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

# Main chat interface
# Display chat messages from history on app rerun
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

    # --- Agentic Execution Loop ---
    if st.session_state.get("agentic_mode_enabled") and st.session_state.get("agentic_plan"):
        plan = st.session_state.agentic_plan
        agentic_state = st.session_state.agentic_state # This is a dict
        
        current_step_idx = agentic_state.get("current_step_index", 0)
        executed_call_count = agentic_state.get("executed_call_count", 0)
        step_limit = st.session_state.get("agentic_step_limit", 10)

        st.info(f"🤖 Agentic Mode: Executing Plan ({current_step_idx}/{len(plan)} steps completed, {executed_call_count}/{step_limit} calls made)")
        if len(plan) > 0:
            st.progress(current_step_idx / len(plan))

        # Check if call limit reached
        if executed_call_count >= step_limit:
            if not agentic_state.get("limit_reached_flag", False): # Prevent multiple summaries if stuck
                summarize_and_log_agentic_results(agentic_state, plan_completed=False, limit_reached=True)
                st.warning(f"Agentic execution stopped: Call limit of {step_limit} reached. Partial results (if any) logged.")
                agentic_state["limit_reached_flag"] = True
                st.session_state.agentic_plan = None # Stop further execution
                st.session_state.agentic_state = default_agentic_state_values.copy()
                st.button("Acknowledge & Clear Plan", on_click=lambda: setattr(st.session_state, 'agentic_plan', None) or st.rerun())
            # No 'Next Step' button if limit is reached and plan is cleared.

        # Check if plan is still active (not cleared by limit or completion)
        elif st.session_state.get("agentic_plan") and current_step_idx < len(plan):
            step_details = plan[current_step_idx]
            st.markdown(f"**Current Task:** {step_details.get('description', 'No description')}")

            # Placeholder for "Pause/Resume/Abort" later
            # For now, execution proceeds with "Next Step" button

            if st.button(f"Execute Step {current_step_idx + 1}: {step_details.get('step_id', 'Unnamed')}", key=f"exec_step_{current_step_idx}"):
                with st.spinner(f"Executing: {step_details.get('description', 'Working...')}"):
                    try:
                        print(f"CHAT_APP_ST [DEBUG]: st.session_state.agentic_state BEFORE execute_step call for step {current_step_idx + 1}: {st.session_state.agentic_state}")
                        execution_result = execute_step(step_details, st.session_state.agentic_state) # Pass the session state directly
                        st.toast(f"DEBUG: execute_step returned: {execution_result.get('status')}", icon="📋") # DEBUG
                        
                        # Update agentic_state with the returned state from execute_step
                        st.session_state.agentic_state = execution_result.get("updated_agentic_state", agentic_state)
                        st.session_state.agentic_state["executed_call_count"] = executed_call_count + 1

                        if execution_result.get("status") == "failure":
                            error_msg = f"Step {current_step_idx + 1} ('{step_details.get('step_id', 'Unnamed')}') failed: {execution_result.get('message', 'Unknown error')}"
                            st.error(error_msg)
                            if "error_messages" not in st.session_state.agentic_state:
                                st.session_state.agentic_state["error_messages"] = []
                            st.session_state.agentic_state["error_messages"].append(error_msg)
                            summarize_and_log_agentic_results(st.session_state.agentic_state, plan_completed=False)
                            st.session_state.agentic_plan = None # Stop plan
                            st.session_state.agentic_state = default_agentic_state_values.copy()
                            st.rerun()
                        elif execution_result.get("requires_user_input", False):
                            st.info(f"Step {current_step_idx + 1} requires user input: {execution_result.get('message', '')}")
                            # UI for user input would go here. For now, just pauses.
                            st.rerun() # Rerun to show info and wait for next interaction
                        else: # Success
                            st.toast(f"DEBUG: Step {current_step_idx + 1} success path reached.", icon="✅") # DEBUG
                            st.session_state.agentic_state["current_step_index"] = current_step_idx + 1
                            st.success(f"Step {current_step_idx + 1} completed. {execution_result.get('message', '')}")
                            st.rerun() # Rerun to process next step or finalize
                    except Exception as e:
                        st.exception(e)
                        st.error(f"An unexpected error occurred during step execution: {e}")
                        # Clear plan to stop further execution on error
                        st.session_state.agentic_plan = None 
                        st.session_state.agentic_state = default_agentic_state_values.copy()
                        st.rerun() # Rerun to show the error and reflect cleared plan
            # If button not clicked, Streamlit script just ends, preserving state for next interaction.
        
        # Check if plan completed (and not already handled by limit/error)
        elif st.session_state.get("agentic_plan") and current_step_idx >= len(plan):
            if not agentic_state.get("completion_logged_flag", False): # Prevent multiple summaries
                summarize_and_log_agentic_results(agentic_state, plan_completed=True)
                st.success("🎉 Agentic plan fully completed!")
                agentic_state["completion_logged_flag"] = True # Mark as logged
                st.session_state.agentic_plan = None # Clear the completed plan
                st.session_state.agentic_state = default_agentic_state_values.copy() # Reset state
                st.balloons()
                st.button("Acknowledge & Clear", on_click=lambda: setattr(st.session_state, 'agentic_plan', None) or st.rerun())
    # --- End Agentic Execution Loop ---

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

        # Agentic Mode: Planning Step
        attempt_agentic_planning = st.session_state.get("agentic_mode_enabled", False)
        new_plan_generated_and_stored = False

        if attempt_agentic_planning:
            # Reset plan and state before attempting to generate a new one from this prompt
            st.session_state.agentic_plan = None 
            st.session_state.agentic_state = default_agentic_state_values.copy() # Assumes default_agentic_state_values is defined

            with st.spinner("Planner is thinking about a multi-step approach..."):
                plan = generate_plan(prompt, st.session_state) # Pass current session state for context
            
            if plan:
                st.session_state.agentic_plan = plan
                new_plan_generated_and_stored = True
                st.info("🤖 Agentic plan generated. Preparing for execution.")
                with st.expander("View Generated Plan", expanded=True):
                    if st.session_state.agentic_plan:
                        for i, step_data in enumerate(st.session_state.agentic_plan):
                            st.markdown(f"**Step {i+1}:** {step_data.get('description', 'No description')}")
                    else:
                        st.markdown("No plan details available.")
                st.rerun() # Rerun to let the (future) execution block pick up the plan
        
        # Normal message processing (if not st.rerun()'d due to new agentic plan)
        # This block executes if: 
        #   1. Agentic mode is OFF, OR
        #   2. Agentic mode is ON, but generate_plan(prompt) returned None (no specific plan for this query)
        if not new_plan_generated_and_stored: # Check if a rerun was already triggered
            if st.session_state.get("bot_initialized_successfully") and "bot" in st.session_state:
                with st.spinner("Thinking..."):
                    try:
                        response = st.session_state.bot.process_message(prompt)
                        # Ensure assistant's response is added to history and displayed
                        if response: # Make sure there's a response to add/display
                            st.session_state.bot.chat_history.append({"role": "assistant", "content": response})
                            with st.chat_message("assistant"):
                                st.markdown(response)
                        # No explicit st.rerun() here, standard Streamlit flow.
                    except Exception as e:
                        st.error(f"Error processing message: {e}")
                        traceback.print_exc(file=sys.stderr)
                        error_message_for_chat = f"Sorry, I encountered an error: {e}"
                        st.session_state.bot.chat_history.append({"role": "assistant", "content": error_message_for_chat})
                        with st.chat_message("assistant"):
                            st.markdown(error_message_for_chat)
            # No need for the 'elif not st.session_state.get("bot_initialized_successfully")' here,
            # as it's handled at the beginning of the prompt processing.e check the error details below.")
            
            # Show initialization diagnostics again if available
            if "initialization_steps" in st.session_state:
                with st.expander("Initialization Diagnostic Details", expanded=True):
                    for step in st.session_state["initialization_steps"]:
                        if step.startswith("✓"):
                            st.success(step)
                        elif step.startswith("⚠️"):
                            st.warning(step)
                        else:
                            st.error(step)
            
            # Add a refresh button
            if st.button("Refresh and Try Again"):
                st.session_state.clear()  # Clear session state to force complete reinitialization
                st.rerun()  # Rerun the app to start fresh
        else: 
             st.error("Chatbot is not ready. Please try refreshing the page.")

    st.sidebar.title("Controls")
    if "batch_mode" not in st.session_state:
        st.session_state.batch_mode = False # Initialize if not present
    st.session_state.batch_mode = st.sidebar.checkbox(
        "Batch Mode", value=st.session_state.batch_mode, key="batch_mode_checkbox"
    )

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
