
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Machine Learning-based Query Classifier

Replaces regex-based classification with an ML model that assigns user queries
to predefined categories with confidence scores.

Categories:
- email_search: Queries related to finding emails
- triage: Queries about urgent/important items needing attention
- catch_up: Queries about what's been missed or pending
- clarify: Questions about previous actions or requests for explanation
- general_chat: General conversation not fitting other categories
"""

from typing import Tuple, Dict
import logging
import joblib
import numpy as np
from pathlib import Path


logger = logging.getLogger(__name__)


class ClassifierError(Exception):
    """Custom exception for classifier-related errors"""
    pass


class MLQueryClassifier:
    """ML-based query classifier using a trained model"""

    def __init__(self, model_path: str):
        """
        Initialize the classifier with a pre-trained model
        
        Args:
            model_path: Path to the joblib file containing the trained model and vectorizer
        
        Raises:
            ClassifierError: If the model cannot be loaded
        """
        try:
            self.model_path = Path(model_path)
            if not self.model_path.exists():
                raise ClassifierError(f"Model file not found at {model_path}")
            
            # Load the model and vectorizer from the joblib file
            model_data = joblib.load(self.model_path)
            
            # Extract model components
            self.vectorizer = model_data.get('vectorizer')
            self.model = model_data.get('model')
            self.label_mapping = model_data.get('label_mapping', {})
            self.confidence_threshold = model_data.get('confidence_threshold', 0.20)
            
            if not self.vectorizer or not self.model:
                raise ClassifierError("Invalid model file: missing vectorizer or model")
                
            logger.info(f"Loaded ML classifier model from {model_path}")
            logger.info(f"Model has {len(self.label_mapping)} classes: {list(self.label_mapping.values())}")
            
        except Exception as e:
            error_msg = f"Failed to initialize ML classifier: {str(e)}"
            logger.error(error_msg)
            raise ClassifierError(error_msg) from e
    
    def preprocess_text(self, text: str) -> str:
        """
        Preprocess the input text for classification
        
        Args:
            text: The raw input text
            
        Returns:
            Preprocessed text
        """
        # Basic preprocessing - lowercase and strip whitespace
        # The vectorizer will handle tokenization and feature extraction
        return text.lower().strip()
    
    def predict(self, text: str) -> Tuple[str, float, Dict[str, float]]:
        """
        Predict the category of a query with confidence scores
        
        Args:
            text: The user's query text
            
        Returns:
            Tuple of (predicted_label, confidence, all_probabilities_dict)
            
        Raises:
            ClassifierError: If prediction fails
        """
        try:
            if not text or not text.strip():
                return "clarify", 1.0, {"clarify": 1.0}
            
            # Preprocess the text
            processed_text = self.preprocess_text(text)
            
            # Transform the text using the vectorizer
            features = self.vectorizer.transform([processed_text])
            
            # Get prediction probabilities
            probabilities = self.model.predict_proba(features)[0]
            
            # Map indices to labels and create a dictionary of all probabilities
            all_probs = {}
            for i, prob in enumerate(probabilities):
                label = self.label_mapping.get(i, f"unknown_{i}")
                all_probs[label] = float(prob)  # Convert numpy float to Python float
            
            # Get the highest probability and its index
            max_prob = max(probabilities)
            max_idx = np.argmax(probabilities)
            predicted_label = self.label_mapping.get(max_idx, "ambiguous")
            
            # If confidence is too low, return ambiguous
            if max_prob < self.confidence_threshold:
                logger.warning(f"Low confidence classification ({max_prob:.2f}): '{text[:50]}...' -> '{predicted_label}'")
                # We'll return the original predicted label, but with the low confidence score
                # The calling code can decide to treat this as ambiguous based on the confidence
            
            logger.info(f"Classified '{text[:50]}...' as '{predicted_label}' with confidence {max_prob:.2f}")
            
            return predicted_label, float(max_prob), all_probs
            
        except Exception as e:
            error_msg = f"Prediction error: {str(e)}"
            logger.error(error_msg)
            raise ClassifierError(error_msg) from e

