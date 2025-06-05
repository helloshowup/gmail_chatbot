import logging
from typing import Any, Dict

import streamlit as st

from gmail_chatbot.agentic_executor import (
    execute_step,
    summarize_and_log_agentic_results,
    handle_step_limit_reached,
)

logger = logging.getLogger(__name__)

# Default state template for agentic execution
default_agentic_state_values: Dict[str, Any] = {
    "current_step_index": 0,
    "executed_call_count": 0,
    "accumulated_results": {},
    "error_messages": [],
}


def run_agentic_plan() -> None:
    """Execute the plan stored in ``st.session_state.agentic_plan``."""
    plan = st.session_state.get("agentic_plan")
    if not plan:
        return
    if not isinstance(plan, list):
        logger.info("Parsing error: agentic_plan is not a list")
        return

    agentic_state = st.session_state.get(
        "agentic_state", default_agentic_state_values.copy()
    )
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
        with st.spinner(
            f"Executing: {step_details.get('description', 'Working...')}"
        ):
            try:
                execution_result = execute_step(step_details, agentic_state)
            except Exception as exc:  # pragma: no cover - defensive
                st.exception(exc)
                st.error(
                    f"An unexpected error occurred during step execution: {exc}"
                )
                st.session_state.agentic_plan = None
                st.session_state.agentic_state = (
                    default_agentic_state_values.copy()
                )
                return

        agentic_state = execution_result.get("updated_agentic_state", agentic_state)
        agentic_state["executed_call_count"] = agentic_state.get(
            "executed_call_count", 0
        ) + 1

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
            "result_keys": list(
                agentic_state.get("accumulated_results", {}).keys()
            ),
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
            st.session_state.agentic_state = (
                default_agentic_state_values.copy()
            )
            st.rerun()
        else:
            st.stop()
