#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Updates the ML classifier model to include preference detection capability.

This script extends the existing ML classifier by adding a new 'preference_update'
category and retraining the model with additional examples to detect when
users are expressing preferences that should be stored in memory.
"""

import sys
import joblib
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

# Add the parent directory to sys.path to import modules properly
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import preference examples
from ml_classifier.preference_training_data import get_preference_training_data, get_non_preference_examples

# Set up logging
logger = logging.getLogger(__name__)

# Define paths
MODEL_DIR = Path(__file__).parent
MODEL_PATH = MODEL_DIR / "classifier_model.joblib"
BACKUP_PATH = MODEL_DIR / "classifier_model.backup.joblib"

def load_existing_training_data():
    """Load existing training data from the model file."""
    try:
        if not MODEL_PATH.exists():
            logger.error(f"No existing model found at {MODEL_PATH}")
            return None, None
            
        # Load the existing model to extract training data
        model_data = joblib.load(MODEL_PATH)
        
        if 'training_data' not in model_data:
            logger.warning("No training data found in the model file")
            return None, None
            
        # Extract the existing X and y
        X = model_data['training_data']['X']
        y = model_data['training_data']['y']
        
        logger.info(f"Loaded existing training data with {len(X)} examples")
        return X, y
        
    except Exception as e:
        logger.error(f"Error loading existing training data: {str(e)}")
        return None, None

def create_updated_model():
    """Create updated model with preference detection capability."""
    # Load existing training data
    X_existing, y_existing = load_existing_training_data()
    
    # Prepare preference training examples
    preference_examples = get_preference_training_data()
    X_preference = preference_examples
    y_preference = ['preference_update'] * len(preference_examples)
    
    # Add some negative examples to ensure balance
    non_preference = get_non_preference_examples()
    
    # Combine the datasets if existing data is available
    if X_existing is not None and y_existing is not None:
        # Create a backup of the existing model
        if MODEL_PATH.exists():
            joblib.dump(joblib.load(MODEL_PATH), BACKUP_PATH)
            logger.info(f"Created backup of existing model at {BACKUP_PATH}")
        
        # Combine existing data with new preference examples
        X = np.concatenate([X_existing, X_preference, non_preference])
        y = np.concatenate([
            y_existing, 
            y_preference, 
            # Assign existing categories to non-preference examples to avoid bias
            np.random.choice(['email_search', 'triage', 'catch_up', 'clarify', 'general_chat'], 
                             size=len(non_preference))
        ])
    else:
        # We don't have existing data, create minimal training set
        # This is just a fallback and will likely have poor performance
        logger.warning("No existing training data found, creating minimal training set")
        X = np.concatenate([X_preference, non_preference])
        y = np.concatenate([
            y_preference,
            # Use balanced categories for the minimal dataset
            ['email_search'] * (len(non_preference) // 5) +
            ['triage'] * (len(non_preference) // 5) +
            ['catch_up'] * (len(non_preference) // 5) +
            ['clarify'] * (len(non_preference) // 5) +
            ['general_chat'] * (len(non_preference) // 5 + len(non_preference) % 5)
        ])
    
    # Create train/test split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Create and train the classifier pipeline
    pipeline = Pipeline([
        ('vectorizer', TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_df=0.85)),
        ('classifier', LogisticRegression(C=1.0, max_iter=1000, class_weight='balanced'))
    ])
    
    # Train the model
    pipeline.fit(X_train, y_train)
    
    # Evaluate the model
    y_pred = pipeline.predict(X_test)
    logger.info("\nClassification Report:\n" + classification_report(y_test, y_pred))
    
    # Check preference detection specifically
    preference_test = [ex for i, ex in enumerate(X_test) if y_test[i] == 'preference_update']
    if preference_test:
        preference_pred = pipeline.predict(preference_test)
        pref_accuracy = sum(pred == 'preference_update' for pred in preference_pred) / len(preference_test)
        logger.info(f"Preference detection accuracy: {pref_accuracy:.2f}")
    
    # Save the trained model along with metadata
    model_data = {
        'pipeline': pipeline,
        'classes': pipeline.classes_.tolist(),
        'training_data': {
            'X': X,
            'y': y
        },
        'version': '1.1',  # Increment version to indicate preference detection capability
        'trained_date': pd.Timestamp.now().isoformat()
    }
    
    joblib.dump(model_data, MODEL_PATH)
    logger.info(f"Updated model saved to {MODEL_PATH}")
    
    return model_data

if __name__ == "__main__":
    logger.info("Updating ML classifier with preference detection capability...")
    create_updated_model()
    logger.info("Model update complete.")
