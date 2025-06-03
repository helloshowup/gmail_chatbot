# Gmail Chatbot Assistant

A Claude-powered chatbot that interacts with your Gmail account. This tool allows you to search, analyze, and extract information from your emails using natural language queries. All requests and responses are processed through the Claude API to ensure privacy and contextual understanding.

## Features

- Natural language Gmail search queries (e.g., "Find emails from John about the project meeting")
- Email content analysis and summarization
- Information extraction from email threads
- User-friendly GUI interface
- Secure OAuth2 authentication with Gmail API
- Claude API integration for intelligent processing

## Prerequisites

- Python 3.8 or higher
- Claude API key
- Google Cloud Platform project with Gmail API enabled
- OAuth 2.0 client credentials (client_secret.json)

## Setup Instructions

### 1. Claude API Setup

1. Sign up for an Anthropic API key at [https://console.anthropic.com/](https://console.anthropic.com/)
2. The tool uses the existing `.env` file in the main project directory at `C:\Users\User\Documents\showup-v4\.env` which should contain:

   ```env
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   ```

   (This key should already be present in your .env file)

### 2. Google Cloud Setup

1. Create a project in the [Google Cloud Console](https://console.cloud.google.com/)
2. Enable the Gmail API for your project
3. Configure the OAuth consent screen
4. Create OAuth 2.0 credentials and download the `client_secret.json` file
5. Place the `client_secret.json` file in the `data` directory

### 3. Installation

Run the `run_email_chatbot.bat` script, which will:

- Create a virtual environment
- Install required dependencies
- Check for required configuration files
- Start the application

## Usage

1. Launch the application using `run_email_chatbot.bat`
2. First-time users will be prompted to authorize the application to access their Gmail account
3. Enter natural language queries in the chat interface to interact with your emails

### Example Queries

- "Find emails from Sarah sent last week"
- "Show me emails with attachments about the budget proposal"
- "Find any emails mentioning the client meeting scheduled for tomorrow"
- "Search for emails with the subject containing 'quarterly report'"

## Privacy and Security

- All email content is processed locally on your machine
- Claude API is used to interpret queries and format responses
- OAuth2 authentication ensures secure access to your Gmail account
- No email content is stored permanently by the application

## Troubleshooting

### Authentication Issues

If you encounter authentication errors with Gmail API:

1. Delete the `token.json` file in the `data` directory
2. Restart the application and go through the authentication flow again

### API Key Issues

If you see Claude API errors:

1. Verify your API key in the `.env` file
2. Check that your Claude API subscription is active

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
python email_vector_db.py --reindex
```

This will create a new FAISS index using all emails in memory, optimized for your hardware.

### Verifying GPU Acceleration

To check if GPU acceleration is active:

```bash
python email_vector_db.py
```

The output will display `GPU acceleration: True` if successfully enabled.

## License

This project is for personal use only.
