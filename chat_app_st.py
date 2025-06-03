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

# Initialize chat history

# Initialize chatbot app instance if not already done
if "bot" not in st.session_state and not st.session_state.get("initialization_attempted", False):
    st.session_state["initialization_attempted"] = True # Mark that we are attempting initialization

    # Load .env file before checking for the API key
    dotenv_path = Path(__file__).resolve().parent / ".env"
    if dotenv_path.exists():
        dotenv.load_dotenv(dotenv_path)
        # st.sidebar.info(f"Loaded .env from {dotenv_path}") # Optional: for debugging
    # else:
        # st.sidebar.warning(f".env file not found at {dotenv_path}") # Optional: for debugging

    # Check for Anthropic API key before attempting to initialize
    print(f"DEBUG: os module right before use: {os}", file=sys.stderr)
    if not os.environ.get(CLAUDE_API_KEY_ENV):
        st.error(f"Missing {CLAUDE_API_KEY_ENV} environment variable. Please set it in your .env file or environment.")
        st.warning("The application cannot start without the API key.")
        st.session_state["bot_initialized_successfully"] = False
        st.stop() # Stop execution if key is missing
    else:
        # API key is present, proceed with initialization
        st.info("Initializing chatbot... This might take a moment on the first run while AI models are downloaded and set up.")
        with st.spinner("Please wait: Setting up AI model and connecting to services... This may take several minutes."):
            try:
                st.session_state["initialization_steps"] = [] # Initialize early
                st.session_state["initialization_steps"].append("Attempting to import GmailChatbotApp...")
                print("DEBUG: chat_app_st.py - BEFORE GmailChatbotApp import", file=sys.stderr)
                print(f"DEBUG: chat_app_st.py - sys.path JUST BEFORE IMPORT: {sys.path}", file=sys.stderr)
                try:
                    print("DEBUG: chat_app_st.py - Attempting import of GmailChatbotApp from email_main...", file=sys.stderr)
                    from email_main import GmailChatbotApp # Deferred import
                    print("DEBUG: chat_app_st.py - Import statement for GmailChatbotApp COMPLETED.", file=sys.stderr)
                    
                    if 'GmailChatbotApp' in locals() and isinstance(GmailChatbotApp, type):
                        print("DEBUG: chat_app_st.py - GmailChatbotApp is a class/type as expected.", file=sys.stderr)
                    elif 'GmailChatbotApp' in locals():
                        print(f"CRITICAL_DEBUG: chat_app_st.py - GmailChatbotApp was imported but is NOT a class/type! Type is: {type(GmailChatbotApp)}", file=sys.stderr)
                        raise RuntimeError(f"GmailChatbotApp imported but is not a class. Type: {type(GmailChatbotApp)}")
                    else:
                        print("CRITICAL_DEBUG: chat_app_st.py - GmailChatbotApp not in locals after import! This should not happen.", file=sys.stderr)
                        raise RuntimeError("GmailChatbotApp not defined after import.")

                    st.session_state["initialization_steps"].append("✓ GmailChatbotApp imported successfully")
                    st.session_state["gmail_chatbot_app_imported"] = True # Mark as imported
                    print("DEBUG: chat_app_st.py - Session state updated after successful import.", file=sys.stderr)
                except ImportError as import_err:
                    print(f"CRITICAL_DEBUG: chat_app_st.py - FAILED to import GmailChatbotApp: {import_err}", file=sys.stderr)
                    traceback.print_exc(file=sys.stderr)
                    st.session_state["initialization_steps"].append(f"✗ FAILED to import GmailChatbotApp: {import_err}")
                    raise # Re-raise to be caught by outer try-except
                
                # Step 1: Initialize autonomous task counter
                try:
                    if "autonomous_task_counter" not in st.session_state:
                        st.session_state["autonomous_task_counter"] = 0
                    st.session_state["initialization_steps"].append("✓ Autonomous task counter initialized")
                except Exception as counter_error:
                    st.session_state["initialization_steps"].append(f"✗ Failed to initialize autonomous task counter: {counter_error}")
                    raise
                
                # Step 2: Create GmailChatbotApp instance
                st.session_state["initialization_steps"].append("Attempting to create GmailChatbotApp instance...")
                try:
                    print("DEBUG: chat_app_st.py - BEFORE GmailChatbotApp instantiation", file=sys.stderr)
                    st.session_state["bot"] = GmailChatbotApp(autonomous_counter_ref=st.session_state)
                    print("DEBUG: chat_app_st.py - AFTER GmailChatbotApp instantiation: SUCCESS", file=sys.stderr)
                    st.session_state["initialization_steps"].append("✓ GmailChatbotApp instance created successfully")
                except Exception as app_error:
                    print(f"CRITICAL_DEBUG: chat_app_st.py - FAILED to instantiate GmailChatbotApp: {app_error}", file=sys.stderr)
                    traceback.print_exc(file=sys.stderr)
                    st.session_state["initialization_steps"].append(f"✗ Failed to create GmailChatbotApp: {app_error}")
                    raise
                
                # Step 3: Verify that required components are initialized
                try:
                    # Check required components
                    required_components = [
                        ("chat_history", "Chat history"),
                        ("claude_client", "Claude API client"),
                        ("gmail_client", "Gmail API client"),
                        ("memory_store", "Memory store"),
                        ("process_message", "Message processor")
                    ]
                    
                    for attr, name in required_components:
                        if not hasattr(st.session_state["bot"], attr):
                            st.session_state["initialization_steps"].append(f"✗ Missing required component: {name}")
                            raise AttributeError(f"Bot instance is missing required component: {name}")
                    
                    # Verify Google API connection
                    st.session_state["initialization_steps"].append("Attempting to verify Google API connection...")
                    print("DEBUG: chat_app_st.py - BEFORE gmail_client.test_connection()", file=sys.stderr)
                    api_status = st.session_state["bot"].gmail_client.test_connection()
                    print(f"DEBUG: chat_app_st.py - AFTER gmail_client.test_connection(), status: {api_status}", file=sys.stderr)
                    if not api_status.get('success', False):
                        st.session_state["initialization_steps"].append(f"⚠️ Google API connection warning/failure: {api_status.get('message', 'Unknown error')}")
                    else:
                        st.session_state["initialization_steps"].append("✓ Google API connection verified successfully")
                    
                    st.session_state["initialization_steps"].append("✓ All required components and API connection checked")
                except Exception as verify_error:
                    st.session_state["initialization_steps"].append(f"✗ Component verification failed: {verify_error}")
                    raise
                
                # All checks passed, mark initialization as successful
                st.session_state["bot_initialized_successfully"] = True
            except Exception as e:
                # sys and traceback are imported at the top of the file.
                traceback.print_exc(file=sys.stderr)
                st.error(f"Error during chatbot initialization: {e}")
                
                # Display detailed initialization diagnostics
                if "initialization_steps" in st.session_state:
                    st.error("Initialization failed with the following diagnostics:")
                    for step in st.session_state["initialization_steps"]:
                        if step.startswith("✓"):
                            st.success(step)
                        elif step.startswith("⚠️"):
                            st.warning(step)
                        else:
                            st.error(step)
                
                st.error("Please check the console logs for more details. The application might not work correctly.")
                st.session_state["bot_initialized_successfully"] = False
                # We don't st.stop() here to allow user to see the error, but bot won't work.
        
        if st.session_state.get("bot_initialized_successfully"):
            st.success("Chatbot initialized successfully!") 
            time.sleep(2) # Pause for 2 seconds for user to see success message
        st.rerun() # Rerun to clear spinner/info and proceed based on success

# Main chat interface
# Show if initialization was successful, or if it failed (to show errors and allow retry by refresh)
if st.session_state.get("initialization_attempted", False):

    # Display chat messages from history on app rerun
    if "bot" in st.session_state and hasattr(st.session_state.bot, "chat_history"):
        for message in st.session_state.bot.chat_history: # Use bot's history
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    # Accept user input
    if prompt := st.chat_input("Ask me about your inbox:"):
        with st.chat_message("user"):
            st.markdown(prompt)

        if st.session_state.get("bot_initialized_successfully") and "bot" in st.session_state:
            with st.spinner("Thinking..."):
                try:
                    # process_message will internally update bot.chat_history with user and assistant messages
                    _ = st.session_state["bot"].process_message(prompt)
                    st.rerun() # Rerun to display the updated chat history from bot.chat_history
                except Exception as e:
                    st.error(f"Error processing message: {e}")
                    with st.chat_message("assistant"):
                        st.markdown(f"Sorry, I encountered an error: {e}")
        elif not st.session_state.get("bot_initialized_successfully"):
            st.error("Chatbot initialization failed. Please check the error details below.")
            
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
