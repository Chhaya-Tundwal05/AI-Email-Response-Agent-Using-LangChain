import os
import psycopg2
from datetime import datetime

def connect_to_postgres():
    """Connect to Google Cloud PostgreSQL instance."""
    try:
        conn = psycopg2.connect(
            host=os.environ.get('DB_HOST'),
            port=os.environ.get('DB_PORT', 5432),
            database=os.environ.get('DB_NAME'),
            user=os.environ.get('DB_USER'),
            password=os.environ.get('DB_PASSWORD')
        )
        return conn
    except Exception as e:
        print(f"Error connecting to PostgreSQL: {e}")
        return None

def verify_existing_table(conn):
    """Verify the existing email table has all required columns."""
    with conn.cursor() as cursor:
        # Check if the table exists
        cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'emails'
        );
        """)
        
        table_exists = cursor.fetchone()[0]
        
        if not table_exists:
            print("Table 'emails' does not exist. Please ensure the table exists with the following columns:")
            print("- email_id (PRIMARY KEY)")
            print("- sender_email")
            print("- subject")
            print("- body")
            print("- received_at")
            print("- classified_category")
            print("- status")
            print("- escalated")
            return False
            
        return True

def update_email_status(conn, email_id, status, response_body=None):
    """Update email status in database."""
    try:
        cursor = conn.cursor()
        if response_body:
            cursor.execute('''
                UPDATE emails 
                SET status = %s, response_body = %s, responded_at = %s
                WHERE email_id = %s
            ''', (status, response_body, datetime.now(), email_id))
        else:
            cursor.execute('''
                UPDATE emails 
                SET status = %s
                WHERE email_id = %s
            ''', (status, email_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating email status: {e}")
        conn.rollback()
        return False 