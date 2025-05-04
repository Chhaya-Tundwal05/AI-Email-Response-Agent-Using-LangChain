# escalation/escalator.py

class Escalator:
    def __init__(self, cursor, conn, threshold=0.5):
        self.cursor = cursor
        self.conn = conn
        self.threshold = threshold

    def should_escalate(self, confidence: float) -> bool:
        return confidence < self.threshold

    def escalate(self, email_id: int, reason: str):
        self.cursor.execute("""
            INSERT INTO escalations (email_id, reason)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
        """, (email_id, reason))
        self.conn.commit()
        print(f"🚨 Escalated Email ID {email_id}: {reason}")
