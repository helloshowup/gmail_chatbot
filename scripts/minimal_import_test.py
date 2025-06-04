# c:\Users\User\Documents\showup-v4\showup-tools\gmail_chatbot\minimal_import_test.py
import os
import sys
import time
import traceback

print(f"[{time.time():.3f}] Starting minimal_import_test.py from {__file__}")

# Adjust sys.path to include the 'showup-tools' directory.
# For this script located in 'gmail_chatbot', 'showup-tools' is one level up ('..').
project_root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

if project_root_dir not in sys.path:
    sys.path.insert(0, project_root_dir)
    print(f"[{time.time():.3f}] Added {project_root_dir} to sys.path")
else:
    print(f"[{time.time():.3f}] {project_root_dir} already in sys.path")

print(f"[{time.time():.3f}] Current sys.path[0]: {sys.path[0]}")

try:
    print(f"[{time.time():.3f}] Attempting to import google.auth.transport.requests...")
    print(f"[{time.time():.3f}] Successfully imported google.auth.transport.requests")

    print(f"[{time.time():.3f}] Attempting to import GmailAPIClient from gmail_chatbot.email_gmail_api...")
    # This will execute all module-level code in email_gmail_api.py
    print(f"[{time.time():.3f}] Successfully imported GmailAPIClient")

except KeyboardInterrupt:
    print(f"[{time.time():.3f}] KeyboardInterrupt caught during imports.")
    traceback.print_exc()
except Exception as e:
    print(f"[{time.time():.3f}] Error during import: {e}")
    traceback.print_exc()

print(f"[{time.time():.3f}] Finished minimal_import_test.py")
