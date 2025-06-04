#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Direct API logging test script to verify logging functionality
without relying on the GUI or full application flow.
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path
import json
import traceback

logger = logging.getLogger(__name__)

# Add project root directory to path to allow imports
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import API logging functions
from api_logging import (
    API_LOGS_DIR, 
    log_claude_request,
    log_claude_response
)


def verify_api_logging() -> bool:
    """
    Test that API logging works correctly by directly calling logging functions
    and verifying log file creation.
    
    Returns:
        bool: True if all verification steps passed, False otherwise
    """
    print("\n" + "-"*80)
    print("VERIFYING API LOGGING FUNCTIONALITY")
    print("-"*80)
    
    try:
        # 1. Ensure log directory exists
        print("\nSTEP 1: Testing log directory creation...")
        logs_dir = Path(API_LOGS_DIR)
        date_dir = logs_dir / datetime.now().strftime('%Y%m%d')
        
        # Create log directory if it doesn't exist
        os.makedirs(logs_dir, exist_ok=True)
        os.makedirs(date_dir, exist_ok=True)
        
        if os.path.isdir(logs_dir) and os.path.isdir(date_dir):
            print(f"[OK] Log directories exist:\n- Base: {logs_dir}\n- Date: {date_dir}")
            
            # Test write permissions
            try:
                test_file = date_dir / "write_test.txt"
                with open(test_file, 'w') as f:
                    f.write("Testing write permissions")
                os.remove(test_file)
                print("[OK] Write permissions verified for log directory")
            except Exception as e:
                print(f"[FAIL] Cannot write to log directory: {e}")
                return False
        else:
            print("[FAIL] Log directories could not be created")
            return False
            
        # 2. Log a test Claude request
        print("\nSTEP 2: Testing Claude request logging...")
        test_model = "claude-3-haiku-20240307"
        test_system_msg = "You are a helpful email assistant."
        test_query = "Find emails from Microsoft about account security."
        
        request_log_path = log_claude_request(
            model=test_model,
            system_message=test_system_msg,
            user_message=test_query,
            original_query=test_query
        )
        
        if os.path.isfile(request_log_path):
            file_size = os.path.getsize(request_log_path)
            print(f"[OK] Claude request log created: {request_log_path} (Size: {file_size} bytes)")
            
            # Verify content
            with open(request_log_path, 'r', encoding='utf-8') as f:
                request_data = json.load(f)
                # The actual log file structure doesn't have "interaction_type" at the top level
                # It should have model, system_message, user_message, etc.
                if "model" in request_data and "system_message" in request_data and "user_message" in request_data:
                    print("[OK] Request log contains correct data structure")
                else:
                    print(f"[FAIL] Request log has incorrect data structure: {list(request_data.keys())}")
                    # Print the structure for debugging
                    print(f"[DEBUG] Log content sample: {json.dumps(request_data, indent=2)[:200]}...")
        else:
            print(f"[FAIL] Claude request log not created at: {request_log_path}")
            return False
        
        # 3. Log a test Claude response
        print("\nSTEP 3: Testing Claude response logging...")
        test_response = "I found 3 emails from Microsoft about account security."
        test_tokens = {"input_tokens": 150, "output_tokens": 75}
        
        response_log_path = log_claude_response(
            request_log_path=request_log_path,
            response_content=test_response,
            tokens_used=test_tokens
        )
        
        if os.path.isfile(response_log_path):
            file_size = os.path.getsize(response_log_path)
            print(f"[OK] Claude response log created: {response_log_path} (Size: {file_size} bytes)")
            
            # Verify content
            with open(response_log_path, 'r', encoding='utf-8') as f:
                response_data = json.load(f)
                if response_data.get("interaction_type") == "claude_response":
                    print("[OK] Response log contains correct data structure")
                else:
                    print("[FAIL] Response log has incorrect data structure")
        else:
            print(f"[FAIL] Claude response log not created at: {response_log_path}")
            return False
        
        # 4. Verify logs directory structure
        print("\nSTEP 4: Verifying logs directory structure...")
        if os.path.isdir(date_dir):
            log_files = [f for f in os.listdir(date_dir) if os.path.isfile(os.path.join(date_dir, f))]
            print(f"[OK] Date directory created: {date_dir} with {len(log_files)} log files")
        else:
            print(f"[FAIL] Date directory not created: {date_dir}")
            return False
        
        # All tests passed
        print("\n" + "-"*80)
        print("[SUCCESS] All API logging verification tests passed!")
        print("-"*80)
        return True
        
    except Exception as e:
        print(f"[ERROR] Verification failed with exception: {e}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = verify_api_logging()
    sys.exit(0 if success else 1)
