from googleapiclient.errors import HttpError
from hr_email_responder_agent.gmail_integration.gmail_auth import get_gmail_service

service = get_gmail_service()
print("✅ Gmail service created successfully")


try:
    # Call the Gmail API to fetch the latest 5 messages
    results = service.users().messages().list(userId='me', maxResults=5).execute()
    messages = results.get('messages', [])

    if not messages:
        print("No messages found.")
    else:
        print("Recent Emails:")
        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
            for header in msg_data['payload']['headers']:
                if header['name'] == 'Subject':
                    print("✉️ Subject:", header['value'])

except HttpError as error:
    print(f"An error occurred: {error}")