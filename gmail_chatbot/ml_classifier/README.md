# ML Query Classifier for Gmail Chatbot

This ML-based query classifier replaces the regex-based approach in the Gmail Chatbot, providing more accurate classification of user queries into the following categories:

- **email_search**: Queries related to finding emails
- **triage**: Queries about urgent/important items needing attention
- **catch_up**: Queries about what's been missed or pending
- **clarify**: Questions about previous actions or requests for explanation
- **general_chat**: General conversation not fitting other categories

## Quick Start

### Prerequisites

- Python 3.8+
- Required packages: scikit-learn, pandas, numpy, joblib

### Using the Classifier

The classifier is automatically used by the Gmail Chatbot system. The existing `query_classifier.py` now uses the ML-based classifier as its primary classification method, with the regex-based approach as a fallback only if the ML classifier fails.

```python
# Example code showing how the classifier is called
from gmail_chatbot.query_classifier import classify_query_type

query = "Search my inbox for invoices from ABC."
query_type, confidence, all_scores = classify_query_type(query)

print(f"Classified as: {query_type}, confidence: {confidence:.2f}")
print(f"All scores: {all_scores}")
```

## Retraining the Model

The classifier can be retrained with new data as it becomes available in the logs.

### Standard Training

```bash
# Run from the ml_classifier directory
python update_classifier.py
```

This will:

1. Extract training data from logs
2. Preprocess the text
3. Train and optimize the model using grid search
4. Evaluate performance on a test set
5. Save the model to `classifier_model.joblib`

### Semi-Supervised Learning

For incremental improvements using unlabeled data:

```bash
# Run from the ml_classifier directory
python update_classifier.py --semi-supervised
```

This will:

1. Use the existing model to generate high-confidence predictions on new data from logs
2. Add these as new training examples
3. Retrain the model with the augmented dataset

## Data Preparation

The classifier requires labeled data in CSV format with at least two columns:

- `text`: The user query
- `label`: The classification category

Place your data files in the project data directory or specify a path when running the training script.

## Performance Metrics

The classifier currently achieves approximately 85-90% accuracy on the test set, with precision and recall varying by category. Triage and email_search typically have the highest precision, while clarify has the highest recall.

## Troubleshooting

- If the model fails to load, check that the `classifier_model.joblib` file exists in the ml_classifier directory.
- If classification accuracy seems poor, retrain the model with more varied examples.
- If you encounter import errors, ensure all dependencies are installed.

## Integration

The ML classifier is integrated with the existing system through the `query_classifier.py` module, which now calls the ML classifier first and falls back to regex only if needed.
