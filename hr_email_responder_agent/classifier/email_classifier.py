# classifier/email_classifier.py

from transformers import pipeline

# Load model once at the top (keeps it in memory)
classifier = pipeline(
    "zero-shot-classification",
    model="facebook/bart-large-mnli",
    device=-1  # -1 = CPU, 0 = GPU if available
)

def classify_email(subject: str, body: str, candidate_labels: list) -> tuple:
    """
    Classifies an email using subject + body and returns predicted label & confidence.
    """
    email_text = f"{subject}\n\n{body}"
    
    result = classifier(email_text, candidate_labels, multi_label=False)
    predicted_desc = result['labels'][0]
    confidence = result['scores'][0]
    
    return predicted_desc, confidence