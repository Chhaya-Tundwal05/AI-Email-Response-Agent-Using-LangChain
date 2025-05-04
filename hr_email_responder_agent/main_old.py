from db.connection import connect_db
from classifier.email_classifier import classify_email
from utils.constants import candidate_labels, label_mapping
from escalation.escalator import Escalator

# Function to fetch unclassified emails
def fetch_unclassified_emails(cursor):
    cursor.execute("""
        SELECT email_id, subject, body
        FROM emails
        WHERE classified_category IS NULL
    """)
    return cursor.fetchall()

if __name__ == "__main__":
    # Establish DB connection
    conn = connect_db()
    if not conn:
        raise Exception("❌ Failed to connect to the database")

    cursor = conn.cursor()

    escalator = Escalator(cursor=cursor, conn=conn, threshold=0.5)

    # Fetch emails
    emails_to_classify = fetch_unclassified_emails(cursor)

    # Loop through each and classify
    for email_id, subject, body in emails_to_classify:
        predicted_label, confidence = classify_email(subject, body, candidate_labels)

        if escalator.should_escalate(confidence):
            reason = f"Confidence below threshold: {confidence:.2f}"
            escalator.escalate(email_id, reason)
            cursor.execute("""
                UPDATE emails
                SET classified_category = %s,
                    escalated = TRUE
                WHERE email_id = %s
            """, (predicted_label, email_id))
        else:
            cursor.execute("""
                UPDATE emails
                SET classified_category = %s,
                    escalated = FALSE
                WHERE email_id = %s
            """, (predicted_label, email_id))

        conn.commit()

        print(f"📩 Email ID {email_id}")
        print(f"🧠 Predicted: {predicted_label}")
        print(f"📈 Confidence: {round(confidence, 2)}\n")