import os
import imaplib
import email
from email.header import decode_header
import re
import psycopg2
from datetime import datetime
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from transformers import pipeline, AutoModelForCausalLM, AutoTokenizer
import urllib3
import certifi
import hashlib
import json
import requests

# Disable SSL verification warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Set SSL certificate path
os.environ['SSL_CERT_FILE'] = certifi.where()

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

def clean_text(text):
    """Clean and normalize text content."""
    if text is None:
        return ""
    
    # Convert to string if it's not already
    if not isinstance(text, str):
        text = str(text)
    
    # Replace multiple whitespace with single space
    text = re.sub(r'\s+', ' ', text)
    
    # Remove any non-printable characters
    text = ''.join(c for c in text if c.isprintable() or c in ['\n', '\t'])
    
    return text.strip()

def decode_email_header_text(header):
    """Decode email header."""
    if header is None:
        return ""
    
    result = ""
    decoded_header = decode_header(header)
    
    for content, encoding in decoded_header:
        if isinstance(content, bytes):
            try:
                if encoding:
                    content = content.decode(encoding)
                else:
                    content = content.decode('utf-8', errors='replace')
            except Exception:
                content = content.decode('utf-8', errors='replace')
        result += str(content)
    
    return result

def get_email_body(msg):
    """Extract email body from message."""
    body = ""
    
    if msg.is_multipart():
        # If the email has multiple parts, try to find the text/plain part
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            
            # Skip attachments
            if "attachment" in content_disposition:
                continue
                
            if content_type == "text/plain":
                try:
                    body = part.get_payload(decode=True).decode('utf-8', errors='replace')
                    break
                except Exception as e:
                    print(f"Error decoding plain text: {e}")
            
            # If no text/plain is found, try text/html
            elif content_type == "text/html" and not body:
                try:
                    html_body = part.get_payload(decode=True).decode('utf-8', errors='replace')
                    # Simple HTML tag removal - consider using BeautifulSoup for better results
                    body = re.sub(r'<[^>]+>', ' ', html_body)
                except Exception as e:
                    print(f"Error decoding HTML: {e}")
    else:
        # If the email is not multipart
        try:
            body = msg.get_payload(decode=True).decode('utf-8', errors='replace')
        except Exception as e:
            print(f"Error decoding email body: {e}")
            body = ""
    
    return clean_text(body)

def extract_sender_email(from_header):
    """Extract email address from From header."""
    if not from_header:
        return ""
        
    # Try to extract email from format: "Name <email@example.com>"
    email_match = re.search(r'<([^>]+)>', from_header)
    if email_match:
        return email_match.group(1)
    
    # If no angle brackets, return as is (likely just an email address)
    return from_header.strip()

def parse_date(date_str):
    """Parse date from email header."""
    if not date_str:
        return datetime.now()
        
    try:
        # Try to parse various date formats
        date_formats = [
            '%a, %d %b %Y %H:%M:%S %z',
            '%a, %d %b %Y %H:%M:%S %Z',
            '%d %b %Y %H:%M:%S %z',
            '%a, %d %b %Y %H:%M:%S',
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        
        # If all formats fail, use current time
        return datetime.now()
    except Exception:
        return datetime.now()

def get_classifier():
    """Initialize and return the email classifier."""
    try:
        # Setup classifier with online model
        classifier = pipeline(
            "zero-shot-classification",
            model="facebook/bart-large-mnli",
            device_map="auto"
        )
        return classifier
    except Exception as e:
        print(f"Error loading model: {e}")
        return None

def classify_email(classifier, subject, body):
    """Classify an email using the classifier."""
    if not classifier:
        return None, 0.0

    # Define labels
    label_map = {
        "Leave Request": "Requests related to taking leave or vacation",
        "Onboarding": "Questions about new hire onboarding or joining formalities",
        "Job Offer": "Inquiries regarding job offers or employment contracts",
        "Payroll Inquiry": "Questions related to salary, payslips, or payroll processing",
        "Benefits Inquiry": "Questions about insurance, medical, or employee benefits",
        "Resignation & Exit": "Emails about resignation, exit process, or final settlements",
        "Attendance & Timesheet": "Issues about work hours, attendance or timesheets",
        "Recruitment Process": "Questions about interview, screening or hiring stages",
        "Policy Clarification": "Clarification about company policies or procedures",
        "Training & Development": "Queries about training programs or skill development",
        "Work From Home Requests": "Requests or updates regarding remote work",
        "Relocation & Transfer": "Inquiries about internal transfers or relocation",
        "Expense Reimbursement": "Questions about reimbursements or expense claims",
        "IT & Access Issues": "Issues about system access, accounts, or technical problems",
        "Events & Celebrations": "Emails about office events, parties, or celebrations"
    }

    descriptive_labels = list(label_map.values())
    email_text = f"Subject: {subject}\nBody: {body}"

    try:
        result = classifier(email_text, descriptive_labels)
        predicted_description = result["labels"][0]
        confidence = result["scores"][0]

        predicted_label = next(
            key for key, value in label_map.items() if value == predicted_description
        )

        return predicted_label, confidence
    except Exception as e:
        print(f"Error classifying email: {e}")
        return None, 0.0

def get_thread_history(conn, thread_id):
    """Fetch all emails in a thread for context."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT email_id, sender_email, subject, body, received_at, classified_category
        FROM emails
        WHERE thread_id = %s
        ORDER BY received_at ASC
    """, (thread_id,))
    return cursor.fetchall()

def get_llm_response(prompt):
    """Generate response using LLM."""
    try:
        # Initialize the model and tokenizer
        model_name = "microsoft/DialoGPT-large"  # You can change this to any other suitable model
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForCausalLM.from_pretrained(model_name)

        # Generate response
        inputs = tokenizer.encode(prompt + tokenizer.eos_token, return_tensors='pt')
        outputs = model.generate(
            inputs,
            max_length=200,
            pad_token_id=tokenizer.eos_token_id,
            no_repeat_ngram_size=3,
            do_sample=True,
            top_k=100,
            top_p=0.7,
            temperature=0.8
        )
        response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        # Clean up the response
        response = response.replace(prompt, "").strip()
        return response
    except Exception as e:
        print(f"Error generating LLM response: {e}")
        return None

def format_conversation_history(thread_history):
    """Format conversation history for the prompt."""
    formatted_history = []
    for email in thread_history:
        email_id, sender, subject, body, received_at, category = email
        formatted_history.append({
            'sender': sender,
            'subject': subject,
            'body': body,
            'timestamp': received_at.strftime("%Y-%m-%d %H:%M:%S"),
            'category': category
        })
    return formatted_history

def get_category_prompt(category):
    """Get category-specific prompt template."""
    prompt_templates = {
        "Leave Request": """You are an HR assistant handling leave requests. 
        Please generate a professional response that:
        1. Acknowledges the leave request
        2. Requests specific details if not provided (dates, type of leave, reason)
        3. Mentions the leave approval process
        4. Provides information about required documentation
        5. Includes next steps for the employee
        Maintain a supportive and understanding tone while ensuring all necessary information is collected.""",

        "Onboarding": """You are an HR assistant handling new hire onboarding queries. 
        Please generate a welcoming response that:
        1. Acknowledges their interest in joining
        2. Provides a clear onboarding timeline
        3. Lists required documents and information
        4. Mentions any pre-joining formalities
        5. Includes contact information for further queries
        Ensure the response is informative and helps them feel welcome to the organization.""",

        "Job Offer": """You are an HR assistant handling job offer inquiries. 
        Please generate a professional response that:
        1. Acknowledges their interest in the position
        2. Provides clear information about the offer details
        3. Mentions the acceptance timeline
        4. Includes next steps in the process
        5. Offers to clarify any terms or conditions
        Maintain a positive tone while being clear about the offer terms.""",

        "Payroll Inquiry": """You are an HR assistant handling payroll-related queries. 
        Please generate a professional response that:
        1. Acknowledges their payroll concern
        2. Requests specific details if needed (payslip period, specific issues)
        3. Mentions the standard processing timeline
        4. Provides information about payroll policies
        5. Includes next steps for resolution
        Be clear and precise while maintaining confidentiality.""",

        "Benefits Inquiry": """You are an HR assistant handling benefits-related queries. 
        Please generate a helpful response that:
        1. Acknowledges their benefits question
        2. Provides relevant benefits information
        3. Mentions eligibility criteria if applicable
        4. Includes enrollment or modification procedures
        5. Offers to clarify any specific benefits details
        Be informative while maintaining a supportive tone.""",

        "Resignation & Exit": """You are an HR assistant handling resignation and exit process queries. 
        Please generate a professional response that:
        1. Acknowledges their resignation/exit query
        2. Outlines the exit process steps
        3. Mentions required documentation
        4. Provides information about final settlements
        5. Includes next steps in the process
        Maintain a professional and supportive tone throughout.""",

        "Attendance & Timesheet": """You are an HR assistant handling attendance and timesheet issues. 
        Please generate a clear response that:
        1. Acknowledges their attendance/timesheet concern
        2. Requests specific details if needed (dates, issues)
        3. Mentions attendance policies
        4. Provides information about correction procedures
        5. Includes next steps for resolution
        Be precise and helpful while maintaining policy compliance.""",

        "Recruitment Process": """You are an HR assistant handling recruitment process queries. 
        Please generate a professional response that:
        1. Acknowledges their recruitment-related question
        2. Provides information about the current stage
        3. Mentions the next steps in the process
        4. Includes expected timelines
        5. Offers to clarify any specific concerns
        Maintain a positive and informative tone.""",

        "Policy Clarification": """You are an HR assistant handling policy clarification requests. 
        Please generate a clear response that:
        1. Acknowledges their policy question
        2. Provides relevant policy information
        3. Mentions any exceptions or special cases
        4. Includes where to find the complete policy
        5. Offers to clarify any specific points
        Be precise and accurate while maintaining policy compliance.""",

        "Training & Development": """You are an HR assistant handling training and development queries. 
        Please generate an encouraging response that:
        1. Acknowledges their interest in training/development
        2. Provides information about available programs
        3. Mentions eligibility criteria
        4. Includes enrollment procedures
        5. Offers to discuss specific development goals
        Maintain a supportive and encouraging tone.""",

        "Work From Home Requests": """You are an HR assistant handling work from home requests. 
        Please generate a professional response that:
        1. Acknowledges their WFH request
        2. Requests specific details if needed (dates, reason)
        3. Mentions WFH policies and guidelines
        4. Provides information about required approvals
        5. Includes next steps in the process
        Be clear about policies while maintaining flexibility.""",

        "Relocation & Transfer": """You are an HR assistant handling relocation and transfer requests. 
        Please generate a professional response that:
        1. Acknowledges their relocation/transfer request
        2. Requests specific details if needed (location, timing)
        3. Mentions relocation policies and benefits
        4. Provides information about the transfer process
        5. Includes next steps and required approvals
        Be clear about the process while maintaining a supportive tone.""",

        "Expense Reimbursement": """You are an HR assistant handling expense reimbursement queries. 
        Please generate a clear response that:
        1. Acknowledges their expense reimbursement request
        2. Requests specific details if needed (expenses, receipts)
        3. Mentions reimbursement policies
        4. Provides information about the submission process
        5. Includes next steps and expected timeline
        Be precise about requirements while maintaining a helpful tone.""",

        "IT & Access Issues": """You are an HR assistant handling IT and access-related issues. 
        Please generate a helpful response that:
        1. Acknowledges their IT/access concern
        2. Requests specific details about the issue
        3. Mentions standard resolution procedures
        4. Provides information about IT support channels
        5. Includes next steps for resolution
        Be clear about the process while maintaining a supportive tone.""",

        "Events & Celebrations": """You are an HR assistant handling event and celebration queries. 
        Please generate an enthusiastic response that:
        1. Acknowledges their event-related message
        2. Provides information about upcoming events
        3. Mentions participation details
        4. Includes any registration requirements
        5. Encourages participation
        Maintain an enthusiastic and welcoming tone."""
    }
    return prompt_templates.get(category, """You are an HR assistant. 
    Please generate a professional and helpful response that:
    1. Acknowledges the email appropriately
    2. References the conversation history if it's a follow-up
    3. Maintains a professional and helpful tone
    4. Provides appropriate next steps or updates""")

def generate_contextual_response(thread_history, current_email, classifier):
    """Generate a response using LLM based on the conversation history."""
    # Format the conversation history
    formatted_history = format_conversation_history(thread_history)
    
    # Get category-specific prompt
    category_prompt = get_category_prompt(current_email['classified_category'])
    
    # Create the prompt for the LLM
    prompt = f"""{category_prompt}

    Conversation History:
    {json.dumps(formatted_history, indent=2)}

    Current Email:
    Sender: {current_email['sender_email']}
    Subject: {current_email['subject']}
    Category: {current_email['classified_category']}
    Confidence: {current_email['confidence']}

    Please generate a response that:
    1. Acknowledges the email appropriately
    2. References the conversation history if it's a follow-up
    3. Addresses the specific category of the request
    4. Maintains a professional and helpful tone
    5. Provides appropriate next steps or updates

    Response:"""

    # Get response from LLM
    response = get_llm_response(prompt)
    
    # If LLM fails, fall back to template response
    if not response:
        if len(thread_history) > 1:
            response = f"Thank you for your follow-up email regarding '{current_email['subject']}'. "
            if current_email['classified_category']:
                response += f"This appears to be a {current_email['classified_category']} request. "
            response += "We are actively working on your request and will provide an update soon."
        else:
            if current_email['classified_category']:
                response = f"Thank you for your email regarding '{current_email['subject']}'. This appears to be a {current_email['classified_category']} request. We have received your message and will process it accordingly."
            else:
                response = f"Thank you for your email regarding '{current_email['subject']}'. We have received your message and will process it accordingly."
    
    return response

def process_email_response(conn, email_id, sender_email, subject, body, smtp_username, smtp_password, classifier):
    """Process and send response for an email."""
    try:
        # Classify the email
        category, confidence = classify_email(classifier, subject, body)
        
        # Get thread ID for this email
        cursor = conn.cursor()
        cursor.execute("""
            SELECT thread_id 
            FROM emails 
            WHERE email_id = %s
        """, (email_id,))
        thread_id = cursor.fetchone()[0]
        
        # Get conversation history
        thread_history = get_thread_history(conn, thread_id)
        
        # Update classification in database
        cursor.execute('''
            UPDATE emails 
            SET classified_category = %s,
                classification_confidence = %s,
                escalated = CASE
                    WHEN %s < 0.2 THEN TRUE
                    ELSE FALSE
                END
            WHERE email_id = %s
        ''', (category, confidence, confidence, email_id))
        conn.commit()

        # Skip sending response if category is human_intervention
        if category == "human_intervention":
            print(f"Skipping response for email {email_id} as it requires human intervention")
            return True

        # Generate contextual response using LLM
        current_email = {
            'sender_email': sender_email,
            'subject': subject,
            'classified_category': category,
            'confidence': confidence
        }
        response_body = generate_contextual_response(thread_history, current_email, classifier)

        # Send the response
        if send_email_response(sender_email, subject, response_body, smtp_username, smtp_password):
            # Update status in database
            update_email_status(conn, email_id, 'RESPONDED', response_body)
            return True
        return False
    except Exception as e:
        print(f"Error processing email response: {e}")
        return False

def send_email_response(sender_email, subject, response_body, smtp_username, smtp_password):
    """Send email response using SMTP."""
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = smtp_username
        msg['To'] = sender_email
        msg['Subject'] = f"Re: {subject}"

        # Add body
        msg.attach(MIMEText(response_body, 'plain'))

        # Connect to Gmail's SMTP server
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(smtp_username, smtp_password)

        # Send email
        server.send_message(msg)
        server.quit()
        
        print(f"Response sent to {sender_email}")
        return True
    except Exception as e:
        print(f"Error sending email response: {e}")
        return False

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

def extract_thread_id(msg, email_id, sender_email):
    """Extract or generate thread ID for an email."""
    # First try to get the In-Reply-To or References header
    in_reply_to = msg.get('In-Reply-To', '')
    references = msg.get('References', '')
    
    # If this is a reply, use the existing thread ID
    if in_reply_to or references:
        # Get the message ID from either In-Reply-To or References
        message_id = in_reply_to if in_reply_to else references.split()[-1]
        # Clean the message ID (remove < and >)
        message_id = message_id.strip('<>')
        # Convert message ID to a numeric hash
        return int(hashlib.md5(message_id.encode()).hexdigest(), 16) % (10**9)
    
    # For new emails, create a unique thread ID
    # Convert binary email_id to integer
    email_id_int = int(email_id.decode('utf-8')) if isinstance(email_id, bytes) else int(email_id)
    # Create a numeric hash of the sender email
    sender_hash = int(hashlib.md5(sender_email.encode()).hexdigest(), 16) % (10**6)
    # Combine to create a unique thread ID
    thread_id = (email_id_int * 1000000) + sender_hash
    return thread_id

def get_email_thread_id(conn, message_id):
    """Get existing thread ID from database if it exists."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT thread_id 
        FROM emails 
        WHERE message_id = %s 
        LIMIT 1
    """, (message_id,))
    result = cursor.fetchone()
    return result[0] if result else None

def fetch_emails_imap(username, password, delete_after_import=False):
    """Fetch emails using IMAP and store them in PostgreSQL."""
    try:
        # Initialize classifier
        classifier = get_classifier()
        if not classifier:
            print("Warning: Could not initialize classifier. Emails will be processed without classification.")

        # Connect to PostgreSQL
        conn = connect_to_postgres()
        if not conn:
            return
        
        if not verify_existing_table(conn):
            return
            
        cursor = conn.cursor()
        
        # Connect to Gmail's IMAP server
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        
        # Login
        mail.login(username, password)
        
        # Select the mailbox
        mail.select("inbox")
        
        # Search for unread emails only
        status, messages = mail.search(None, "UNSEEN")
        
        if status != 'OK':
            print(f"Error searching for unread emails: {status}")
            return
        
        # Convert messages to a list of email IDs
        email_ids = messages[0].split()
        
        if not email_ids:
            print("No unread emails found.")
            return
        
        # First, collect all emails
        collected_emails = []
        print("Collecting emails...")
        
        for email_id in reversed(email_ids):  # Process newest emails first
            # Fetch the email
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            
            if status != 'OK':
                print(f"Error fetching email {email_id}: {status}")
                continue
            
            # Parse the email content
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    # Extract headers
                    subject = decode_email_header_text(msg.get("Subject", ""))
                    from_header = msg.get("From", "")
                    sender_email = extract_sender_email(from_header)
                    date_str = msg.get("Date", "")
                    message_id = msg.get("Message-ID", "").strip('<>')
                    
                    # Parse date
                    received_at = parse_date(date_str)
                    
                    # Get email body
                    body = get_email_body(msg)
                    
                    # Extract or generate thread ID
                    thread_id = extract_thread_id(msg, email_id, sender_email)
                    
                    # Store email data
                    collected_emails.append({
                        'email_id': email_id,
                        'sender_email': sender_email,
                        'subject': subject,
                        'body': body,
                        'received_at': received_at,
                        'message_id': message_id,
                        'thread_id': thread_id
                    })
        
        print(f"Collected {len(collected_emails)} emails.")
        
        # Now process each collected email
        emails_processed = 0
        print("\nProcessing emails...")
        
        for email_data in collected_emails:
            try:
                # Set default values for columns not in email
                classified_category = None  # Default category
                status = 'NOT RESPONDED'  # Default status
                escalated = False  # Default escalation status
                
                # Check if this is a reply and get the thread ID
                if email_data['message_id']:
                    existing_thread_id = get_email_thread_id(conn, email_data['message_id'])
                    if existing_thread_id:
                        email_data['thread_id'] = existing_thread_id
                
                # Insert email into database
                cursor.execute('''
                INSERT INTO emails (
                    sender_email, subject, body, received_at, 
                    classified_category, status, escalated,
                    message_id, thread_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING email_id
                ''', (
                    email_data['sender_email'], 
                    email_data['subject'], 
                    email_data['body'], 
                    email_data['received_at'],
                    classified_category, 
                    status, 
                    escalated,
                    email_data['message_id'],
                    email_data['thread_id']
                ))
                
                # Get the inserted email_id
                inserted_email_id = cursor.fetchone()[0]
                conn.commit()
                
                # Process and send response with classification
                process_email_response(
                    conn, 
                    inserted_email_id, 
                    email_data['sender_email'], 
                    email_data['subject'],
                    email_data['body'],
                    username, 
                    password,
                    classifier
                )
                
                emails_processed += 1
                print(f"Processed email with subject: {email_data['subject']}")
                
                # Optionally delete the email after importing
                if delete_after_import:
                    mail.store(email_data['email_id'], '+FLAGS', '\\Deleted')
                    
            except Exception as e:
                conn.rollback()
                print(f"Error processing email: {e}")
        
        # Expunge deleted messages if any
        if delete_after_import:
            mail.expunge()
            
        # Close the connection
        mail.close()
        mail.logout()
        
        print(f"\nSuccessfully processed {emails_processed} emails.")
    
    except Exception as e:
        print(f"An error occurred: {e}")
    
    finally:
        if 'conn' in locals() and conn:
            conn.close()

def main():
    """Main function."""
    try:
        # Set up environment variables for database connection
        os.environ['DB_HOST'] = '34.59.119.208'
        os.environ['DB_PORT'] = '5432'
        os.environ['DB_NAME'] = 'postgres'
        os.environ['DB_USER'] = 'postgres'
        os.environ['DB_PASSWORD'] = 'avantichhaya'
        
        # Disable SSL verification for requests
        requests.packages.urllib3.disable_warnings()
        os.environ['CURL_CA_BUNDLE'] = ""
        
        # Your Gmail credentials
        username = "avanaya3@gmail.com"
        password = "eivp yrwm qfxi qimn"
        
        # Fetch emails using IMAP
        fetch_emails_imap(username, password, delete_after_import=False)
        
    except Exception as e:
        print(f"An error occurred in the main function: {e}")

if __name__ == '__main__':
    main() 