# agentic_executor.py
import logging
from datetime import datetime, date
import streamlit as st
from typing import Dict, Any, Optional
from gmail_chatbot.memory_writers import store_professional_context

# Define a type for the result of execute_step for clarity
execute_step_result = Dict[str, Any]

# Module level logger
logger = logging.getLogger(__name__)

# --- Tool/Action Implementations (Placeholders for now, to be made real) ---

def _execute_search_inbox(parameters: Dict[str, Any], agentic_state: Dict[str, Any]) -> Dict[str, Any]:
    """Search the user's Gmail inbox using the app's Gmail client."""
    query = parameters.get("query", "")
    max_results = parameters.get("max_results", 5)

    gmail_client = getattr(getattr(st.session_state, "bot", None), "gmail_client", None)
    system_message = getattr(getattr(st.session_state, "bot", None), "system_message", "")
    if gmail_client is None:
        return {"status": "failure", "message": "Gmail client not available"}

    try:
        emails, response_text = gmail_client.search_emails(
            query,
            original_user_query=query,
            system_message=system_message,
            request_id=None,
        )
        if isinstance(emails, list) and max_results:
            emails = emails[:max_results]
        return {"status": "success", "data": emails, "message": response_text}
    except Exception as e:  # pragma: no cover - defensive
        return {"status": "failure", "message": f"Gmail search failed: {e}"}

def _execute_extract_entities(parameters: Dict[str, Any], agentic_state: Dict[str, Any]) -> Dict[str, Any]:
    """Use Claude to extract structured entities from prior step output."""
    input_data_key = parameters.get("input_data_key")
    extraction_prompt = parameters.get("extraction_prompt", "Extract key info.")

    input_data = agentic_state.get("accumulated_results", {}).get(input_data_key)
    if input_data is None:
        return {"status": "failure", "message": f"Input data key '{input_data_key}' not found in accumulated results."}

    claude_client = getattr(getattr(st.session_state, "bot", None), "claude_client", None)
    system_message = getattr(getattr(st.session_state, "bot", None), "system_message", "")
    if claude_client is None:
        return {"status": "failure", "message": "Claude client not available"}

    try:
        entities = claude_client.process_email_content(
            input_data,
            extraction_prompt,
            system_message,
            model=claude_client.prep_model,
        )
        return {"status": "success", "data": entities, "message": "Entities extracted"}
    except Exception as e:  # pragma: no cover - defensive
        return {"status": "failure", "message": f"Entity extraction failed: {e}"}

def _execute_summarize_text(parameters: Dict[str, Any], agentic_state: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize prior step output using Claude."""
    input_data_key = parameters.get("input_data_key")

    input_data = agentic_state.get("accumulated_results", {}).get(input_data_key)
    if input_data is None:
        return {"status": "failure", "message": f"Input data key '{input_data_key}' not found for summarization."}

    claude_client = getattr(getattr(st.session_state, "bot", None), "claude_client", None)
    system_message = getattr(getattr(st.session_state, "bot", None), "system_message", "")
    if claude_client is None:
        return {"status": "failure", "message": "Claude client not available"}

    try:
        prompt = f"Please provide a concise summary of the following information:\n{input_data}"
        summary = claude_client.chat(
            prompt,
            [],
            system_message,
            model=claude_client.prep_model,
        )
        return {"status": "success", "data": summary, "message": "Text summarized"}
    except Exception as e:  # pragma: no cover - defensive
        return {"status": "failure", "message": f"Summarization failed: {e}"}

def _execute_log_to_notebook(parameters: Dict[str, Any], agentic_state: Dict[str, Any]) -> Dict[str, Any]:
    """Persist step output to the notebook using memory_writers utilities."""
    input_data_key = parameters.get("input_data_key")
    notebook_id = parameters.get("notebook_id", "default_notebook")
    section_title = parameters.get("section_title", "Agentic Log")
    overwrite_if_exists = parameters.get("overwrite_if_exists", False)

    input_data = agentic_state.get("accumulated_results", {}).get(input_data_key)
    if input_data is None:
        input_data = "No specific data provided for logging."

    memory_store = getattr(getattr(st.session_state, "bot", None), "enhanced_memory_store", None)
    if memory_store is None:
        memory_store = getattr(getattr(st.session_state, "bot", None), "memory_store", None)
    if memory_store is None:
        return {"status": "failure", "message": "No memory store available for logging."}

    try:
        entry_date = date.today()
        existing_entry = None
        for entry in getattr(memory_store, "memory_entries", []):
            if entry.get("type") == "professional_context":
                try:
                    if datetime.fromisoformat(entry.get("date")).date() == entry_date:
                        existing_entry = entry
                        break
                except Exception:
                    continue

        if existing_entry and not overwrite_if_exists:
            message = (
                f"Professional context already logged for {entry_date}"
            )
            return {
                "status": "skipped",
                "reason": "already_logged",
                "message": message,
            }

        if existing_entry and overwrite_if_exists:
            try:
                memory_store.memory_entries = [
                    e
                    for e in memory_store.memory_entries
                    if e is not existing_entry
                ]
                if hasattr(memory_store, "memory_entries_store"):
                    memory_store.memory_entries_store.save(memory_store.memory_entries)
            except Exception as exc:  # pragma: no cover - defensive
                return {
                    "status": "failure",
                    "message": (
                        f"Failed to overwrite existing entry: {exc}"
                    ),
                }

        store_professional_context(memory_store, section_title, str(input_data))
        confirmation_message = (
            f"Content from '{input_data_key}' logged to notebook '{notebook_id}' under section '{section_title}'."
        )
        return {"status": "success", "data": confirmation_message, "message": confirmation_message}
    except Exception as e:  # pragma: no cover - defensive
        return {"status": "failure", "message": f"Failed to log to notebook: {e}"}

def _execute_send_email(parameters: Dict[str, Any], agentic_state: Dict[str, Any]) -> Dict[str, Any]:
    """Prepare an email and request user confirmation before sending."""
    to = parameters.get("to")
    subject = parameters.get("subject", "")
    body = parameters.get("body", "")

    preview = f"To: {to}\nSubject: {subject}\n\n{body}"
    return {
        "status": "success",
        "data": {"to": to, "subject": subject, "body": body},
        "message": preview,
        "requires_user_input": True,
    }

# --- Placeholder Tool Handlers (from previous version, for testing simple plans) ---
def _execute_placeholder_search(parameters: Dict[str, Any], agentic_state: Dict[str, Any]) -> Dict[str, Any]:
    query = parameters.get("query", "default_query")
    st.toast(f"Executing placeholder search: {query}", icon="🧪")
    return {"status": "success", "data": [f"Simulated search result 1 for '{query}'"], "message": "Placeholder search complete."}

def _execute_placeholder_summarize(parameters: Dict[str, Any], agentic_state: Dict[str, Any]) -> Dict[str, Any]:
    input_data_key = parameters.get("input_data_key")
    input_docs = agentic_state.get("accumulated_results", {}).get(input_data_key, [])
    st.toast(f"Executing placeholder summarize on {len(input_docs)} docs.", icon="🧪")
    return {"status": "success", "data": f"Simulated summary of {len(input_docs)} documents.", "message": "Placeholder summary complete."}


def _execute_placeholder_action(parameters: Dict[str, Any], agentic_state: Dict[str, Any]) -> Dict[str, Any]:
    """Log placeholder action and return skipped status."""
    logger.info("Placeholder action encountered. Parameters=%s", parameters)
    return {
        "status": "skipped",
        "message": "Placeholder action skipped.",
        "updated_agentic_state": agentic_state,
    }


# --- Main Executor Function ---
# Maps action_type to its handler function
ACTION_HANDLERS = {
    "search_inbox": _execute_search_inbox,
    "extract_entities": _execute_extract_entities,
    "summarize_text": _execute_summarize_text,
    "log_to_notebook": _execute_log_to_notebook,
    "send_email": _execute_send_email,
    "placeholder_search_tool": _execute_placeholder_search, # Kept for existing test plan
    "placeholder_summarize_tool": _execute_placeholder_summarize, # Kept for existing test plan
    "placeholder_action": _execute_placeholder_action,
    # Add more real action handlers here
}

def execute_step(step_details: Dict[str, Any], agentic_state: Dict[str, Any]) -> execute_step_result:
    # --- Original code reinstated (with one toast modification) ---
    action_type = step_details.get("action_type")
    parameters = step_details.get("parameters", {})
    output_key = step_details.get("output_key")
    step_description = step_details.get("description", "Unnamed step")
    step_id = step_details.get("step_id", "N/A")
    logger.info("Starting step %s (%s)", step_id, action_type)
    print(
        f"DEBUG EXECUTOR [START execute_step for {step_id}]: "
        f"Received agentic_state: {agentic_state}"
    )

    # The following st.toast was suspected of causing issues and remains commented out.
    # st.toast(f"Executing: {step_description}", icon="⚙️") 
    print(f"DEBUG EXECUTOR: Attempting step: {step_id} - {step_description}")
    print(f"DEBUG EXECUTOR: Parameters: {parameters}")

    handler = ACTION_HANDLERS.get(action_type)
    if not handler:
        error_message = (
            f"No handler found for action_type: '{action_type}' in step "
            f"'{step_id} - {step_description}'"
        )
        logger.info("Parsing error: %s", error_message)
        print(f"ERROR EXECUTOR: {error_message}")
        return {
            "status": "failure",
            "message": error_message,
            "updated_agentic_state": agentic_state,
            "requires_user_input": False
        }

    try:
        # Pass both parameters from plan and the whole agentic_state to the handler
        # Handlers can choose to use agentic_state to retrieve prior step outputs
        state_to_pass_to_handler = agentic_state.copy()
        print(f"DEBUG EXECUTOR [execute_step for {step_id}]: agentic_state (original) before passing copy to handler: {agentic_state}")
        print(f"DEBUG EXECUTOR [execute_step for {step_id}]: state_to_pass_to_handler (copy) before handler call: {state_to_pass_to_handler}")
        result = handler(parameters, state_to_pass_to_handler) 
        
        status = result.get("status", "failure")
        message = result.get("message", "No message from step execution.")
        step_output_data = result.get("data")
        
        # The handler should return the modified agentic_state if it changes it.
        # For safety, we take the updated_agentic_state from the result if provided.
        updated_agentic_state = result.get("updated_agentic_state", agentic_state)

        # Update accumulated_results in the potentially updated agentic_state
        if output_key and status == "success":
            if "accumulated_results" not in updated_agentic_state:
                updated_agentic_state["accumulated_results"] = {}
            # Ensure accumulated_results is a dict, not a list as seen in previous logs
            if not isinstance(updated_agentic_state["accumulated_results"], dict):
                 updated_agentic_state["accumulated_results"] = {} # Reset if it's not a dict
            updated_agentic_state["accumulated_results"][output_key] = step_output_data
            print(f"DEBUG EXECUTOR: Stored output for step {step_id} under key '{output_key}'.")

        state_summary = {
            "executed_call_count": updated_agentic_state.get("executed_call_count"),
            "current_step_index": updated_agentic_state.get("current_step_index"),
            "result_keys": list(updated_agentic_state.get("accumulated_results", {}).keys()),
        }
        logger.info(
            "Finished step %s (%s) status=%s summary=%s",
            step_id,
            action_type,
            status,
            state_summary,
        )
        if status == "skipped":
            logger.info("Step %s skipped: %s", step_id, message)
        
        print(f"DEBUG EXECUTOR: Step '{step_id} - {step_description}' result: {status}. Message: {message}")
        return {
            "status": status,
            "message": message,
            "updated_agentic_state": updated_agentic_state, 
            "requires_user_input": result.get("requires_user_input", False)
        }
    except Exception as e:
        error_message = (
            f"Exception during execution of step '{step_id} - {step_description}'"
            f" ({action_type}): {e}"
        )
        logger.info("Parsing error: %s", error_message)
        print(f"ERROR EXECUTOR: {error_message}")
        import traceback
        traceback.print_exc() # Print full traceback to console
        return {
            "status": "failure",
            "message": error_message,
            "updated_agentic_state": agentic_state, # Return original state on exception
            "requires_user_input": False
        }
    # --- End of original code ---

def summarize_and_log_agentic_results(agentic_state: Dict[str, Any], plan_completed: bool, limit_reached: bool = False) -> None:
    # This function remains largely the same for now, focusing on sidebar display
    # Actual persistent logging will be part of a "log_to_notebook" step or similar.
    st.sidebar.subheader("📋 Agentic Execution Summary")
    if plan_completed:
        st.sidebar.success("Agentic plan completed successfully!")
    elif limit_reached:
        st.sidebar.warning("Agentic execution stopped: Step limit reached.")
    else:
        st.sidebar.info("Agentic execution concluded (or was stopped by error/user).")

    final_results = agentic_state.get("accumulated_results", {})
    if final_results:
        st.sidebar.write("Accumulated Step Outputs:")
        # Display a summary of keys and types, or a sample of data
        for key, value in final_results.items():
            if isinstance(value, list):
                st.sidebar.markdown(f"- **{key}**: List of {len(value)} items")
            elif isinstance(value, dict):
                st.sidebar.markdown(f"- **{key}**: Dictionary with {len(value.keys())} keys")
            else:
                st.sidebar.markdown(f"- **{key}**: (see details below)") # For simple values or large strings
        # Provide an expander for detailed view of all accumulated results
        with st.sidebar.expander("View All Accumulated Data", expanded=False):
            st.json(final_results)

    else:
        st.sidebar.write("No results were accumulated.")
    
    error_messages = agentic_state.get("error_messages", [])
    if error_messages:
        st.sidebar.error("Errors encountered during execution:")
        for err_idx, err in enumerate(error_messages):
            with st.sidebar.expander(f"Error {err_idx+1}", expanded=False):
                 st.markdown(f"{err}")
    
    print(f"DEBUG: Summarize and Log - Final State: {agentic_state}")
    # The actual "logging to notebook" is now a plan step ("log_to_notebook")
    # This function primarily serves to update the UI with the final status.


def handle_step_limit_reached(agentic_state: Dict[str, Any], step_limit: int) -> Optional[str]:
    """Prompt user when the autonomous call limit is reached.

    Returns "continue" if the user chooses to keep going, "stop" if they opt to
    halt execution, or ``None`` if no choice was made."""
    st.warning(
        f"Agentic execution paused: Call limit of {step_limit} reached."
    )
    continue_clicked = st.button("Continue", key="agentic_continue_btn")
    stop_clicked = st.button("Stop", key="agentic_stop_btn")

    if continue_clicked:
        agentic_state["executed_call_count"] = 0
        return "continue"
    if stop_clicked:
        summarize_and_log_agentic_results(
            agentic_state, plan_completed=False, limit_reached=True
        )
        return "stop"
    return None
