# agentic_executor.py
import streamlit as st
from typing import Dict, Any

# Define a type for the result of execute_step for clarity
ExecuteStepResult = Dict[str, Any]

# --- Tool/Action Implementations (Placeholders for now, to be made real) ---

def _execute_search_inbox(parameters: Dict[str, Any], agentic_state: Dict[str, Any]) -> Dict[str, Any]:
    query = parameters.get("query", "")
    max_results = parameters.get("max_results", 5)
    # TODO: Integrate with actual Gmail search client (from st.session_state.bot.gmail_client)
    # For now, simulate
    st.toast(f"Simulating Gmail search for: '{query}' (max {max_results})", icon="🔍")
    print(f"EXECUTOR: Simulating Gmail search for: '{query}', max_results: {max_results}")
    
    # Simulate finding some emails
    simulated_emails = []
    if "bryce hepburn" in query.lower(): # Specific simulation for testing
        simulated_emails = [
            {"id": "email1", "subject": "Project Update - Bryce", "snippet": "Bryce Hepburn mentioned the Q3 targets..."},
            {"id": "email2", "subject": "Meeting with Bryce Hepburn", "snippet": "Scheduled a meeting with Bryce for next week."},
            {"id": "email3", "subject": "Re: Your question", "from": "bryce.hepburn@example.com", "snippet": "Regarding your inquiry..."}
        ]
    elif "agentic ai" in query.lower():
         simulated_emails = [
            {"id": "email_ai1", "subject": "New Agentic AI paper", "snippet": "Check out this research on agentic systems..."},
         ]

    return {"status": "success", "data": simulated_emails, "message": f"{len(simulated_emails)} emails found (simulated)."}

def _execute_extract_entities(parameters: Dict[str, Any], agentic_state: Dict[str, Any]) -> Dict[str, Any]:
    print(f"EXECUTOR_HANDLER [_execute_extract_entities]: Received agentic_state: {agentic_state}")
    retrieved_accumulated_results = agentic_state.get("accumulated_results")
    print(f"EXECUTOR_HANDLER [_execute_extract_entities]: Retrieved accumulated_results from agentic_state: {retrieved_accumulated_results}")

    input_data_key = parameters.get("input_data_key")
    extraction_prompt = parameters.get("extraction_prompt", "Extract key info.")
    
    input_data = agentic_state.get("accumulated_results", {}).get(input_data_key)
    if not input_data:
        return {"status": "failure", "message": f"Input data key '{input_data_key}' not found in accumulated results."}

    # TODO: Integrate with an NLP model/service for entity extraction (e.g., Claude)
    st.toast(f"Simulating entity extraction: {extraction_prompt}", icon="🧩")
    print(f"EXECUTOR: Simulating entity extraction on data from '{input_data_key}'. Prompt: '{extraction_prompt}'")
    
    # Simulate extraction
    simulated_entities = []
    if isinstance(input_data, list) and input_data: # Assuming list of email dicts
        for item_idx, item in enumerate(input_data):
            if isinstance(item, dict) and "snippet" in item:
                 simulated_entities.append(f"Extracted entity from item {item_idx+1}: '{item['snippet'][:30]}...' (simulated)")
            else:
                simulated_entities.append(f"Could not process item {item_idx+1} for entity extraction (simulated)")

    return {"status": "success", "data": simulated_entities, "message": f"{len(simulated_entities)} entities extracted (simulated)."}

def _execute_summarize_text(parameters: Dict[str, Any], agentic_state: Dict[str, Any]) -> Dict[str, Any]:
    input_data_key = parameters.get("input_data_key")
    # summary_length = parameters.get("summary_length", "medium") # Parameter for future use
    
    input_data = agentic_state.get("accumulated_results", {}).get(input_data_key)
    if not input_data:
        return {"status": "failure", "message": f"Input data key '{input_data_key}' not found for summarization."}

    # TODO: Integrate with an NLP model for summarization (e.g., Claude)
    st.toast(f"Simulating text summarization...", icon="📄")
    print(f"EXECUTOR: Simulating summarization on data from '{input_data_key}'.")
    
    # Simulate summarization
    text_to_summarize = str(input_data) # Crude conversion for simulation
    simulated_summary = f"This is a simulated summary of: '{text_to_summarize[:100]}...'"
    return {"status": "success", "data": simulated_summary, "message": "Text summarized (simulated)."}

def _execute_log_to_notebook(parameters: Dict[str, Any], agentic_state: Dict[str, Any]) -> Dict[str, Any]:
    input_data_key = parameters.get("input_data_key")
    notebook_id = parameters.get("notebook_id", "default_notebook")
    section_title = parameters.get("section_title", "Agentic Log")

    input_data = agentic_state.get("accumulated_results", {}).get(input_data_key)
    if input_data is None: # Allow logging even if data is explicitly None (e.g. logging a failure)
        input_data = "No specific data provided for logging."


    # TODO: Implement actual logging to a persistent store/notebook file
    st.toast(f"Simulating logging to notebook: '{notebook_id}'", icon="📝")
    print(f"EXECUTOR: Simulating logging to notebook '{notebook_id}', title '{section_title}'. Data from '{input_data_key}'.")
    print(f"LOGGED CONTENT (simulated):\n---\n{input_data}\n---")
    
    confirmation_message = f"Content from '{input_data_key}' logged to notebook '{notebook_id}' under section '{section_title}' (simulated)."
    return {"status": "success", "data": confirmation_message, "message": confirmation_message}

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


# --- Main Executor Function ---
# Maps action_type to its handler function
ACTION_HANDLERS = {
    "search_inbox": _execute_search_inbox,
    "extract_entities": _execute_extract_entities,
    "summarize_text": _execute_summarize_text,
    "log_to_notebook": _execute_log_to_notebook,
    "placeholder_search_tool": _execute_placeholder_search, # Kept for existing test plan
    "placeholder_summarize_tool": _execute_placeholder_summarize, # Kept for existing test plan
    # Add more real action handlers here
}

def execute_step(step_details: Dict[str, Any], agentic_state: Dict[str, Any]) -> ExecuteStepResult:
    # --- Original code reinstated (with one toast modification) ---
    action_type = step_details.get("action_type")
    parameters = step_details.get("parameters", {})
    output_key = step_details.get("output_key")
    step_description = step_details.get('description', 'Unnamed step')
    step_id = step_details.get('step_id', 'N/A') # Get step_id for logging
    print(f"DEBUG EXECUTOR [START execute_step for {step_id}]: Received agentic_state: {agentic_state}")

    # The following st.toast was suspected of causing issues and remains commented out.
    # st.toast(f"Executing: {step_description}", icon="⚙️") 
    print(f"DEBUG EXECUTOR: Attempting step: {step_id} - {step_description}")
    print(f"DEBUG EXECUTOR: Parameters: {parameters}")

    handler = ACTION_HANDLERS.get(action_type)
    if not handler:
        error_message = f"No handler found for action_type: '{action_type}' in step '{step_id} - {step_description}'"
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
        
        print(f"DEBUG EXECUTOR: Step '{step_id} - {step_description}' result: {status}. Message: {message}")
        return {
            "status": status,
            "message": message,
            "updated_agentic_state": updated_agentic_state, 
            "requires_user_input": result.get("requires_user_input", False)
        }
    except Exception as e:
        error_message = f"Exception during execution of step '{step_id} - {step_description}' ({action_type}): {e}"
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
