from app import app, mail
from flask_mail import Message
import traceback

with app.app_context():
    email_address = app.config.get('MAIL_USERNAME')
    
    print(f"Testing Email Configuration:")
    print(f"Server: {app.config.get('MAIL_SERVER')}:{app.config.get('MAIL_PORT')}")
    print(f"Username loaded: {email_address}")
    
    if not email_address or email_address == 'your-email@gmail.com':
        print("ERROR: It appears the .env file still contains placeholder values or wasn't loaded.")
    else:
        try:
            print("Attempting to send test email...")
            msg = Message("Test OTP Email", recipients=[email_address])
            msg.body = "This is a test email to verify SMTP configuration."
            mail.send(msg)
            print("SUCCESS: SMTP Authentication succeeded and email was sent successfully.")
        except Exception as e:
            print("FAILURE: Email sending failed.")
            print(f"Exact Error Message:\n{str(e)}")
