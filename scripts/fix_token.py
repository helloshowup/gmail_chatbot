#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import pickle
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Configure paths relative to the project root
# This script lives in `scripts/` so the project root is one directory up
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
GMAIL_CLIENT_SECRET_FILE = "client_secret.json"
GMAIL_TOKEN_FILE = "token.json"
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

def create_pickled_token():
    """Create a properly pickled token file from the JSON credential data"""
    creds = None
    token_path = DATA_DIR / GMAIL_TOKEN_FILE
    client_secret_path = DATA_DIR / GMAIL_CLIENT_SECRET_FILE
    
    # Check if we already have a valid pickled token
    if os.path.exists(token_path):
        try:
            with open(token_path, 'rb') as token:
                try:
                    # Try to load as pickle
                    creds = pickle.load(token)
                    if creds and creds.valid:
                        print("Existing pickled token is valid.")
                        return creds
                except Exception as e:
                    print(f"Error loading pickled token: {e}")
                    # Continue to create a new token
        except Exception as e:
            print(f"Error opening token file: {e}")
    
    # No valid credentials, so we need to create them
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                print("Refreshed expired credentials")
            except Exception as e:
                print(f"Error refreshing credentials: {e}")
                creds = None
        
        # If still no valid credentials, get new ones via OAuth flow
        if not creds:
            try:
                print(f"Starting OAuth flow from {client_secret_path}")
                flow = InstalledAppFlow.from_client_secrets_file(
                    client_secret_path, GMAIL_SCOPES)
                creds = flow.run_local_server(port=0)
                print("OAuth flow completed successfully")
            except Exception as e:
                print(f"Error in OAuth flow: {e}")
                raise
    
    # Save the credentials for the next run as pickle
    try:
        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)
        print(f"Credentials saved to {token_path}")
    except Exception as e:
        print(f"Error saving credentials: {e}")
    
    return creds

if __name__ == "__main__":
    print("Gmail API Token Fix Utility")
    print(f"Working directory: {os.getcwd()}")
    print(f"Data directory: {DATA_DIR}")
    print(f"Client secret path: {DATA_DIR / GMAIL_CLIENT_SECRET_FILE}")
    
    # Check if client_secret.json exists
    if not os.path.exists(DATA_DIR / GMAIL_CLIENT_SECRET_FILE):
        print(f"Error: {GMAIL_CLIENT_SECRET_FILE} not found in {DATA_DIR}")
        print("Please ensure you have placed the client_secret.json file in the data directory.")
        exit(1)
    
    # Create the pickled token
    try:
        creds = create_pickled_token()
        print("Token creation/verification successful!")
        print(f"Token expiry: {creds.expiry}")
    except Exception as e:
        print(f"Failed to create/verify token: {e}")
        exit(1)
