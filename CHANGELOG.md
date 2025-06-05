# Gmail Chatbot Changelog

## [Unreleased]

### Added

- Compiled regex patterns for biography queries (`TELL_ME_ABOUT_PATTERN`, `WHO_IS_PATTERN`, etc.) to improve classification
- Centralized `THRESHOLDS` dictionary in query_classifier.py as single source of truth for all confidence values
- Added min_relevance parameter to vector search to filter low-quality results
- Implemented deduplication for vector search results to reduce token usage
- Created `NOTEBOOK_NO_RESULTS_TEMPLATES` in prompt_templates.py for consistent messaging
- Added entity extraction from queries to provide better follow-up suggestions
- Created unit tests for notebook search guard-rail behavior
- Added robust chat initialization guard-rail to Streamlit app to prevent premature user interaction
- Implemented detailed step-by-step initialization diagnostics in chat_app_st.py to provide clear error information
- Added Continue/Stop prompt when autonomous step limit is reached
- INFO level logs for agentic step execution now written to
  `logs/gmail_chatbot/` for troubleshooting
- `CLAUDE_PREP_MODEL` environment variable to configure a cheaper model for
  preparatory steps.
- `CLAUDE_TRIAGE_MODEL` environment variable for inexpensive triage summaries.
- `ClaudeAPIClient.summarize_triage` uses this model for quick inbox triage.
- `ClaudeAPIClient` methods accept an optional `model` argument and expose a
  `prep_model` attribute for inexpensive preprocessing.
- Internal summarization and query-parsing calls route to the prep model while
  user-facing chat continues using the default model.
- Unit tests updated to validate model selection logic.

### Changed

- Raised threshold for general fallback queries to 0.30 while keeping a 0.25 floor for lookup categories
- Improved notebook search guard-rail to prevent hallucinations when no results are found
- Enhanced vector search with relevance score display and formatting
- Made fallback messages more user-friendly with explicit action suggestions
- Updated logger usage to use module-level loggers for better traceability

### Changed

- Removed unused imports across the codebase to satisfy ruff linting

### Fixed

- Corrected email search logic in `_autonomous_memory_enrichment_task` in `email_main.py` by removing erroneous code and restoring proper client-based Gmail API calls and memory storage.
- Implemented correct menu-driven and Claude-assisted email search handling in `process_message` in `email_main.py` for the `email_search` query type.

- Fixed ambiguous classification trap that caused biography queries to use general chat
- Prevented hallucination when notebook search returns no results
- Improved signal-to-noise ratio in vector search by limiting results for low-confidence queries
- Fixed missing Path import in email_main.py that caused Streamlit initialization failure
- Removed duplicate imports for logging and os in email_main.py
- Fixed incorrect function call from logging_shutdown() to shutdown_logging() in email_main.py
- Corrected `sys.path` configuration in `query_classifier.py` to ensure the `ml_query_classifier` module is found, enabling ML-based query classification.
- Updated default `CLAUDE_PREP_MODEL` to `claude-3-haiku-20240307` to avoid model-not-found errors
- Added graceful handling for Anthropic `NotFoundError` when the configured model slug is invalid

## [0.9.0] - 2025-05-15

### Added

- Initial implementation of Gmail Chatbot
- ML-based query classification with regex fallback
- Vector-based memory store for email search
- Claude API integration for natural language processing
