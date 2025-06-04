# AGENTS.MD for Gmail Chatbot Project

## 1. Project Overview

This project is a Gmail Chatbot application designed to interact with a user's Gmail account. It utilizes AI capabilities, including Large Language Models and HuggingFace embeddings, to perform tasks such as searching emails, summarizing content, and executing agentic workflows. The primary interface is built with Streamlit.

## 2. Project Structure

-   **Project Root:** `c:\Users\User\Documents\showup-v4\showup-tools\gmail_chatbot`
-   **Main Application Script:** `chat_app_st.py` (Streamlit UI and application entry point).
-   **Core Logic Modules:**
    -   `email_main.py`: Houses the `GmailChatbotApp` class, which orchestrates the chatbot's core functionalities and agentic behavior.
    -   `email_gmail_api.py`: Manages all interactions with the Gmail API, including authentication, token refresh, email searching, and retrieval. Includes robust SSL error handling.
    -   `email_vector_db.py`: Responsible for initializing and managing HuggingFace sentence embeddings for semantic search. Includes error handling for model loading issues (e.g., `OSError`).
    -   `email_memory_vector.py`: Integrates the vector database with the application's memory system, enabling semantic search over email content.
-   **Configuration:**
    -   `.env`: Located at the project root (`c:\Users\User\Documents\showup-v4\showup-tools\gmail_chatbot\.env`). This file is critical and must contain all necessary environment variables, such as API keys and model names.
-   **Agentic Mode:** The application supports an agentic mode, allowing it to autonomously perform multi-step tasks based on user requests.

## 3. Coding Standards & Best Practices

Adherence to these standards is crucial for maintaining code quality, readability, and consistency.

-   **PEP 8 Compliance:**
    -   Follow Python Enhancement Proposal 8 (PEP 8) for all Python code.
    -   **Naming Conventions:** `snake_case` for functions, methods, and variables; `PascalCase` for classes.
    -   **Line Length:** Maximum 79 characters per line.
    -   **Imports:** Group imports (standard library, third-party, local application) separated by blank lines.
-   **Type Hinting:**
    -   Provide type hints for all function and method signatures (parameters and return types) using the `typing` module.
    -   Strive for specific types (e.g., `List[str]`, `Optional[int]`) over `Any`.
-   **Error Handling & Resilience:**
    -   **Fail-Fast:** Raise or propagate exceptions immediately upon encountering unexpected conditions. Avoid silent failures or overly broad `try-except` blocks that mask issues.
    -   **Specific Exceptions:** Catch specific exceptions rather than generic `Exception`.
    -   **Degraded Mode:** The application should handle failures gracefully. For instance:
        -   If the embedding model fails to load (e.g., `OSError` due to OOM), vector search should be disabled, and the UI must inform the user (`vector_search_available` flag).
        -   If Gmail API calls encounter `ssl.SSLError`, the operation should be skipped or retried with clear logging and user feedback.
    -   (Ref: MEMORY[1f70d373-23c6-4ad5-a038-6b00f6566410])
-   **Modularity & Single Responsibility:**
    -   Modules and classes should have a single, well-defined responsibility.
    -   Break down functions/methods longer than ~30-40 lines into smaller, manageable units.
-   **Readability:**
    -   Write clear, concise, and self-documenting code.
    -   Use descriptive names for variables, functions, and classes.
-   **No Empty Blocks:**
    -   If a function, class, or method body is intentionally empty, use the `pass` statement. (Ref: MEMORY[3a76477d-f212-40d9-a0a3-2e5608e83610])
-   **Logging:** Implement descriptive logging to aid in debugging and monitoring application behavior.

## 4. Dependencies & Environment

-   **Python:** The project is developed in Python.
-   **Key Python Packages:**
    -   `streamlit`: For building the interactive web UI.
    -   `langchain-huggingface`: For using HuggingFace embeddings (specifically `HuggingFaceEmbeddings`). (Ref: MEMORY[98d09f50-d089-4ce1-90cb-890af14f7785])
    -   `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib`: For Gmail API integration.
    -   `python-dotenv`: For managing environment variables from the `.env` file.
-   **Environment Variables:**
    -   All sensitive information (API keys, model names, paths) must be stored in the `.env` file at the project root.
    -   The application relies on this file for proper configuration. (Ref: MEMORY[f286432a-9b3e-482f-9ab9-27d4a5da13b0])

## 5. Running & Testing the Application

-   **Preferred Launch Method:**
    -   Navigate to the project root directory: `cd c:\Users\User\Documents\showup-v4\showup-tools\gmail_chatbot`
    -   Execute the command: `python -m streamlit run chat_app_st.py`
    -   This method is preferred for consistency and to ensure the correct Python environment and module paths are used. (Ref: MEMORY[e6c9aef1-f37f-4dc3-8654-4c5b1949485a], MEMORY[b11168c7-f2ed-4b8b-8a21-0940682c7b39])
    -   *Note on Batch Files:* While `launch_modular_editor.bat` has been mentioned in past contexts (MEMORY[82e35c86-8ab1-4d07-83b7-896510d89aec]), it's confirmed NOT to be part of this specific `gmail_chatbot` project (MEMORY[ff780390-8900-4c1d-9e5e-4c6983ff11a7]). For development and testing of *this* application, use the direct `python -m streamlit run` command.
-   **Testing Gmail API Connection:**
    -   The `GmailAPIClient.test_connection` method provides a structured dictionary output for diagnosing connection issues. This should be used for verifying Gmail API access. (Ref: MEMORY[1f70d373-23c6-4ad5-a038-6b00f6566410])
-   **Vector Search Functionality:**
    -   The UI (`chat_app_st.py`) should display a clear warning (`st.warning`) if vector search capabilities are unavailable due to initialization errors with the embedding model. The application should still function in a degraded mode. (Ref: MEMORY[1f70d373-23c6-4ad5-a038-6b00f6566410])

## 6. Agentic Behavior & Task Execution

-   The application features an "agentic mode" capable of handling complex, multi-step tasks, such as "Do research on X and update Y." (Ref: MEMORY[0897b912-ec08-48f7-8fa6-37afe15a6dbe])
-   Development of agentic features should prioritize:
    -   Clear definition of agent steps and tools.
    -   Robust state management throughout the agent's execution.
    -   Detailed logging of agent actions and decisions.

## 7. Code Modification Guidelines (Refactoring & Development)

-   **Atomic Commits/Changes:** Group related code changes into single, logical units.
-   **Dependency Analysis:** Before moving or refactoring modules/files, analyze the import graph to understand dependencies.
-   **Immediate Reference Updates:** After moving or renaming code, update all import statements and other references throughout the codebase promptly.
-   **Continuous Validation:** After making significant code changes (e.g., adding/modifying ≥100 lines), run the application and test core workflows to ensure no regressions.
-   **Preserve Workflow & Behavior:** Refactoring efforts should not alter existing external APIs or user-facing behavior unless explicitly part of the task.

## 8. AI Assistant (Cascade) Interaction Protocol

-   **Contextual Adherence:** This `AGENTS.MD` file provides the primary context for your operations within this project.
-   **Tool Usage:** When using tools (e.g., `edit_file`, `run_command`), ensure your actions align with the project's structure, coding standards, and testing procedures outlined herein.
-   **Memory Utilization:** Actively use and refer to project-specific memories provided during our interactions to maintain continuity and adhere to established patterns or decisions.
-   **Clarification:** If any instruction in this document or a user request is ambiguous, seek clarification before proceeding.
