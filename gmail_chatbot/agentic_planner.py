# agentic_planner.py
from typing import List, Dict, Any, Optional

# Define type aliases for clarity
plan_step = Dict[str, Any]
plan = List[plan_step]

# --- Predefined Plan Structures/Templates ---
# These could be expanded significantly
# Each function would generate a specific sequence of steps

def _generate_search_summarize_log_plan(search_query: str, log_target: str = "default_notebook") -> plan:
    return [
        {
            "step_id": "search_inbox_initial",
            "description": f"Step 1: Perform initial search in inbox for '{search_query}'.",
            "action_type": "search_inbox", # Corresponds to a handler in agentic_executor
            "parameters": {"query": search_query, "max_results": 10},
            "output_key": "initial_search_results"
        },
        {
            "step_id": "extract_relevant_info",
            "description": "Step 2: Extract key information from search results.",
            "action_type": "extract_entities", # Example: could be more generic like "process_text"
            "parameters": {"input_data_key": "initial_search_results", "extraction_prompt": "Extract names, dates, and key topics."},
            "output_key": "extracted_entities"
        },
        {
            "step_id": "summarize_findings",
            "description": "Step 3: Summarize the extracted information.",
            "action_type": "summarize_text",
            "parameters": {"input_data_key": "extracted_entities", "summary_length": "medium"},
            "output_key": "final_summary"
        },
        {
            "step_id": "log_to_notebook",
            "description": f"Step 4: Log the summary to '{log_target}'.",
            "action_type": "log_to_notebook",
            "parameters": {
                "input_data_key": "final_summary",
                "notebook_id": log_target,
                "section_title": f"Findings for '{search_query}'",
                "overwrite_if_exists": False,
            },
            "output_key": "logging_confirmation",
        }
    ]

# --- Main Planner Function ---
def generate_plan(user_query: str, current_session_state: dict) -> Optional[plan]:
    """
    Generates a multi-step plan based on the user's query using heuristics.
    """
    lower_query = user_query.lower()

    # Heuristic 1: "research X and log/update notebook"
    if ("research" in lower_query or "find out about" in lower_query or "build up understanding" in lower_query) and \
       ("log" in lower_query or "notebook" in lower_query or "update" in lower_query):
        
        # Attempt to extract the core search term (very basic extraction)
        search_term = ""
        if "research" in lower_query:
            search_term = lower_query.split("research", 1)[1].split("and log")[0].split("and update")[0].strip()
        elif "find out about" in lower_query:
            search_term = lower_query.split("find out about", 1)[1].split("and log")[0].split("and update")[0].strip()
        elif "build up understanding" in lower_query: # "Build up your understanding about Bryce Hepburn based on the inbox and log your findings to the notebook.”
             parts = lower_query.split("about", 1)
             if len(parts) > 1:
                 search_term = parts[1].split("based on")[0].split("and log")[0].strip()


        if not search_term: # Fallback if specific keywords aren't perfectly parsed
             # Try to get content between "about" and "and log" or "and update" or "based on"
            if "about " in lower_query:
                temp_term = lower_query.split("about ", 1)[1]
                if " and log" in temp_term:
                    search_term = temp_term.split(" and log")[0].strip()
                elif " and update" in temp_term:
                    search_term = temp_term.split(" and update")[0].strip()
                elif " based on" in temp_term: # Catches "based on the inbox"
                    search_term = temp_term.split(" based on")[0].strip()
                else: # If no clear delimiter, take a few words
                    search_term = " ".join(temp_term.split()[:5]) # Max 5 words
        
        if search_term:
            original_search_term_after_initial_extraction = search_term # For debugging
            
            # Remove potential trailing prepositions like "on", "in" if they are the last word
            if search_term.endswith(" on") or search_term.endswith(" in"):
                search_term = search_term.rsplit(' ', 1)[0]
            
            term_after_trailing_strip = search_term # For debugging

            # New: Remove common leading prepositions
            leading_prepositions = ["on ", "about ", "for ", "of "]
            for prep in leading_prepositions:
                if search_term.startswith(prep):
                    search_term = search_term[len(prep):].strip()
                    break
            
            term_after_leading_prep_strip = search_term # For debugging

            # New: Handle "me (actual_term)" or leading "me "
            if search_term.startswith("me (") and search_term.endswith(")"):
                search_term = search_term[len("me ("):-1].strip()
            elif search_term.startswith("me "):
                search_term = search_term[len("me "):].strip()

            print(f"DEBUG Planner: Initial: '{original_search_term_after_initial_extraction}', AfterTrail: '{term_after_trailing_strip}', AfterLeadPrep: '{term_after_leading_prep_strip}', Final: '{search_term}' for research & log plan.")
            return _generate_search_summarize_log_plan(search_query=search_term)
        else:
            print(f"DEBUG Planner: Could not extract search term for 'research and log' type query: {user_query}")
            # Could return a simpler plan or None
            return None


    # Heuristic 2: Simple "plan a test search and summarize" (keeping the old one for direct testing)
    if "plan a test search and summarize" in lower_query:
        return [
            {
                "step_id": "test_search_step",
                "description": "Step 1: Test search for 'agentic AI'.",
                "action_type": "placeholder_search_tool",
                "parameters": {"query": "agentic AI", "max_results": 3},
                "output_key": "search_results_agentic_ai"
            },
            {
                "step_id": "test_summarize_step",
                "description": "Step 2: Test summarize found documents.",
                "action_type": "placeholder_summarize_tool",
                "parameters": {"input_data_key": "search_results_agentic_ai"},
                "output_key": "summary_of_agentic_ai_docs"
            }
        ]
        
    # Add more heuristics here for other types of requests

    print(f"DEBUG Planner: No specific plan generated for query: {user_query}")
    return None
