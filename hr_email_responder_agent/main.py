import os
from dotenv import load_dotenv

from database.db_connection import connect_to_postgres, verify_existing_table
from email.email_processor import fetch_emails_imap

def main():
    """Main function to run the email processing script."""
    # Load environment variables
    load_dotenv()
    
    # Get database connection parameters from environment variables
    db_params = {
        'dbname': os.getenv('DB_NAME'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
        'host': os.getenv('DB_HOST'),
        'port': os.getenv('DB_PORT', '5432')
    }
    
    # Get Gmail credentials from environment variables
    gmail_username = os.getenv('GMAIL_USERNAME')
    gmail_password = os.getenv('GMAIL_PASSWORD')
    
    if not all([gmail_username, gmail_password]):
        print("Error: Gmail credentials not found in environment variables")
        return
    
    try:
        # Connect to PostgreSQL
        conn = connect_to_postgres(db_params)
        if not conn:
            return
        
        # Verify the emails table exists
        if not verify_existing_table(conn):
            return
        
        # Fetch and process emails
        fetch_emails_imap(gmail_username, gmail_password, conn)
        
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    main() 