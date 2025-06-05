# Gmail Chatbot Assistant

A Claude-powered chatbot that interacts with your Gmail account. This tool allows you to search, analyze, and extract information from your emails using natural language queries. All requests and responses are processed through the Claude API to ensure privacy and contextual understanding.

## Features

- Natural language Gmail search queries (e.g., "Find emails from John about the project meeting")
- Email content analysis and summarization
- Information extraction from email threads
- Streamlit-based web interface
- Tkinter-based GUI provided by the `gui` package (with `email_gui.py` kept as a
  wrapper for backward compatibility)
- Secure OAuth2 authentication with Gmail API
- Claude API integration for intelligent processing
- Vector-based email memory with optional GPU-accelerated search
- Machine learning classifier for understanding query intent
- Cheap triage flow summarizes urgent action items using a low-cost model
- Modular codebase organized under the `gmail_chatbot` package

## Prerequisites

- Python 3.8 or higher
- Claude API key
- Google Cloud Platform project with Gmail API enabled
- OAuth 2.0 client credentials saved as `data/client_secret.json`
- Gmail OAuth token will be stored at `data/token.json`

## Setup Instructions

### 1. Claude API Setup

1. Sign up for an Anthropic API key at [https://console.anthropic.com/](https://console.anthropic.com/)
2. Copy `.env.example` in the project root to `.env` and fill in your key:

   ```env
   ANTHROPIC_API_KEY=your_key_here
   CLAUDE_PREP_MODEL=claude-3-haiku-20240307
   CLAUDE_TRIAGE_MODEL=claude-3-haiku-20240307
   ```
   The application automatically loads this `.env` file at startup via `gmail_chatbot.email_config.load_env()`.
   `CLAUDE_PREP_MODEL` selects the Claude model used to prep email history.
   `CLAUDE_TRIAGE_MODEL` selects the inexpensive model for triage summaries.
   Configure all required environment variables here once.

### 2. Google Cloud Setup

1. Create a project in the [Google Cloud Console](https://console.cloud.google.com/)
2. Enable the Gmail API for your project
3. Configure the OAuth consent screen
4. Create OAuth 2.0 credentials and download the `client_secret.json` file
5. Place your downloaded credentials at `data/client_secret.json`
6. The OAuth process will create `data/token.json` in the same directory.

The application uses the `DATA_DIR` constant in `gmail_chatbot.email_config` to
determine where these files live. By default `DATA_DIR` points to the
`data/` directory at the project root.

### 3. Installation

Run the `run_gmail_chatbot.bat` script, which will:

- Create a virtual environment
- Install required dependencies
- Check for required configuration files
- Start the application

For manual setup you can run one of the provided setup scripts:

```bash
./setup.sh        # Linux/macOS
setup.bat         # Windows
```

Alternatively install the package in editable mode so `gmail_chatbot` can be imported from anywhere:

```bash
pip install -e .
```

These scripts install all packages listed in `requirements.txt`.  A lighter dependency
set is available in `requirements-lite.txt` which omits heavy packages such as
FAISS and PyTorch.  Use this file for CI or limited environments:

```bash
pip install -r requirements-lite.txt
```

## Usage

1. Launch the application using `run_gmail_chatbot.bat`,
   `python -m gmail_chatbot.cli` for the CLI,
   or run `streamlit run chat_app_st.py` for the web UI
2. First-time users will be prompted to authorize the application to access their Gmail account
3. Enter natural language queries in the chat interface to interact with your emails

4. Logging is initialized by the main application using `safe_logger.configure_safe_logging`; individual modules no longer call `logging.basicConfig`.

### Example Queries

- "Find emails from Sarah sent last week"
- "Show me emails with attachments about the budget proposal"
- "Find any emails mentioning the client meeting scheduled for tomorrow"
- "Search for emails with the subject containing 'quarterly report'"

## Streamlit Usage & Best Practices

The main application `chat_app_st.py` demonstrates Streamlit chat widgets such as `st.chat_message` and `st.chat_input` for conversational interaction. Prompt parameters can be tuned via UI controls like sliders, and responses stream back through `st.write_stream` to keep the interface responsive.

Short-term conversation state lives in `st.session_state`; for long-term or multi-user deployments, store history in external persistence (e.g., an EFS volume or database). When running at scale, containerize the app and place it behind a load balancer, applying caching and rate limiting to avoid hitting API quotas.

The autonomous memory enrichment thread is also controlled via `st.session_state`. A flag named `autonomous_thread_started` prevents the enrichment thread from launching more than once per session.

Agentic features use structured prompt templates and few-shot tool examples, allowing the chatbot to reason about tasks and self-correct when necessary.

## Using TASK_CHAIN

When the assistant proposes a plan starting with `TASK_CHAIN:` it outlines a series of steps to run. Review the plan and confirm if you want the chatbot to execute it. If **agentic mode** is enabled in the sidebar the steps run automatically; otherwise reply `yes` to begin or `no` to skip. All Claude and Gmail API calls are saved as JSON logs under `logs/gmail_chatbot_api/<DATE>/`.

## Privacy and Security

- All email content is processed locally on your machine
- Claude API is used to interpret queries and format responses
- OAuth2 authentication ensures secure access to your Gmail account
- No email content is stored permanently by the application

## Troubleshooting

### Authentication Issues

If you encounter authentication errors with Gmail API:

1. Delete the `token.json` file in the project-root `data/` directory
2. Confirm that `data/client_secret.json` exists and is correctly named
3. Restart the application and go through the authentication flow again

Missing or misnamed credentials can prevent the OAuth authorization window from appearing.

### API Key Issues

If you see Claude API errors:

1. Verify your API key in the `.env` file (copied from `.env.example`)
2. Check that your Claude API subscription is active

### Agentic Mode and TASK_CHAIN

- Enable **agentic mode** in the sidebar if you want plans to run automatically.
- When a plan starting with `TASK_CHAIN:` is proposed, reply `yes` to execute or `no` to cancel.
- Check `logs/gmail_chatbot_api/<DATE>/` for JSON logs of Claude and Gmail API calls when debugging.

## GPU Acceleration

The Gmail Chatbot now supports GPU-accelerated vector search using FAISS for significantly faster and more accurate semantic matching:

### GPU/CPU Installation

#### Windows Installation

1. **For NVIDIA GPU acceleration**:
   - Windows requires manual installation of pre-built FAISS wheels:
   - Download the appropriate wheel from one of these sources:
     - [Christoph Gohlke's repository](https://www.lfd.uci.edu/~gohlke/pythonlibs/#faiss)
     - [FAISS Wheels mirror](https://github.com/kyonifer/faiss-wheels/releases)
   - Choose the correct wheel for your Python version and system (e.g., `faiss_gpu-1.7.4.post2-cp311-cp311-win_amd64.whl` for Python 3.11 on 64-bit Windows)
   - Install with pip:

     ```bash
     pip install path/to/downloaded/faiss_gpu-1.7.4.post2-cp311-cp311-win_amd64.whl
     ```
   - Install PyTorch with CUDA support:
     ```bash
     pip install torch==2.2.1+cu118 -f https://download.pytorch.org/whl/torch_stable.html
     ```

2. **For CPU-only version**:
   - Similarly, download the CPU wheel (e.g., `faiss_cpu-1.7.4-cp311-cp311-win_amd64.whl`)
   - Install with pip:
     ```bash
     pip install path/to/downloaded/faiss_cpu-1.7.4-cp311-cp311-win_amd64.whl
     ```

#### Linux/macOS Installation

- Simply install from requirements.txt:
  ```bash
  pip install -r requirements.txt
  ```
- The system will automatically use GPU acceleration if available

### Rebuilding Vector Index

To rebuild the vector index (e.g., after adding many new emails):

```bash
python -m gmail_chatbot.email_vector_db --reindex
```

This will create a new FAISS index using all emails in memory, optimized for your hardware.

### Verifying GPU Acceleration

To check if GPU acceleration is active:

```bash
python -m gmail_chatbot.email_vector_db
```

The output will display `GPU acceleration: True` if successfully enabled.

### Utility Scripts

Helper scripts are stored in the `scripts/` directory:

- **`fix_token.py`** – Regenerates the Gmail OAuth token if it becomes
  corrupted.
  Run with:

  ```bash
  python scripts/fix_token.py
  ```

- **`minimal_import_test.py`** – Quickly verifies that core imports work
  without requiring optional dependencies.
  Run with:

  ```bash
  python scripts/minimal_import_test.py
  ```

- **`verify_logging.py`** – Checks that API logging creates the expected
  log files.
  Run with:

  ```bash
  python scripts/verify_logging.py
  ```

- **`test_guardrail_direct.py`** – Executes a simple guardrail test
  against the chatbot logic.
  Run with:

  ```bash
  python scripts/test_guardrail_direct.py
  ```

### Running Tests

After installing the required dependencies you can run the unit tests with
`pytest`:

```bash
pytest -q
```

If heavy optional dependencies such as FAISS are not available, some tests will
be skipped automatically.

## Code Formatting and Linting

Format code with [black](https://github.com/psf/black) and run
[ruff](https://github.com/astral-sh/ruff) to lint:

```bash
black .

ruff .
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
