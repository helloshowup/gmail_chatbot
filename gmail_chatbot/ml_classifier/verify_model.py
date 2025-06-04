#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Verify that the ML classifier model exists and is valid.
Run this at application startup to fail fast if the model is missing.
"""

import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def verify_model_exists():
    """
    Verify that the classifier model exists and is valid.
    Exits with error code 1 if not found or invalid.
    """
    model_path = Path(__file__).parent / "classifier_model.joblib"
    
    if not model_path.exists():
        logger.error(f"ML classifier model not found at {model_path}")
        logger.error("Run 'python update_classifier.py' to generate the model")
        sys.exit(1)
        
    # Check if file is not empty
    if model_path.stat().st_size < 1000:  # Reasonable minimum size for a valid model
        logger.error("ML classifier model appears to be invalid (too small)")
        logger.error("Run 'python update_classifier.py' to regenerate the model")
        sys.exit(1)
        
    logger.info(f"ML classifier model verified at {model_path}")
    return True


if __name__ == "__main__":
    verify_model_exists()
