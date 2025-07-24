import json
import os
import requests
import smtplib
from email.message import EmailMessage
from email.mime.text import MIMEText
from email.headerregistry import Address
import ssl
import dotenv

dotenv.load_dotenv()

SMTP_SERVER = os.getenv('SMTP_SERVER', 'localhost')
SMTP_PORT = int(os.getenv('SMTP_PORT', 465))
SMTP_USERNAME = os.getenv('SMTP_USERNAME', None)
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', None)


def handle_alert(domain: str, notification: dict, alert_data: dict):
    """
    Handle the alert for a domain.
    """
    alert_type = notification.get('type')

    if alert_type == 'discord_webhook':
        discord_webhook(notification['url'], domain,
                        alert_data, notification['blocks'])
    elif alert_type == 'email':
        email(notification['email'], domain,
              alert_data, notification['blocks'])
    else:
        print(f"Unknown alert type: {alert_type} for domain: {domain}")


def discord_webhook(webhook_url: str, domain: str, content: str, alert_blocks: int):
    """
    Send a message to a Discord webhook.
    """

    data = {
        "username": "FireAlerts",
        "avatar_url": "https://firewallet.au/assets/img/FW.png",
        "components": [
            {
                    "type": 1,
                    "components": [
                        {
                            "type": 2,
                            "style": 5,
                            "url": f"https://alerts.firewallet.au/account/{domain}",
                            "label": "Open your FireAlerts account"
                        }
                    ]
            }
        ],
        "embeds": [
            {
                "author": {
                    "name": "FireAlerts",
                    "icon_url": "https://firewallet.au/assets/img/FW.png"
                },
                "title": f"{domain} is expiring in {content['blocks']} blocks (~{content['time']})",
                "color": 13041919,
                "description": f"You set an alert for {domain}. This domain will expire in {content['blocks']} blocks or approximately {content['time']}.",
                "fields": [
                    {
                        "name": "Domain",
                        "value": domain,
                        "inline": True
                    },
                    {
                        "name": "Notice Blocks",
                        "value": f"{alert_blocks}",
                        "inline": True
                    }
                ]
            }
        ]
    }
    print(json.dumps(data, indent=4))  # Debugging output
    response = requests.post(f"{webhook_url}?with_components=true", json=data)
    if response.status_code != 204:
        print(
            f"Failed to send Discord webhook: {response.status_code} - {response.text}")


def email(email_addr: str, domain: str, content: dict, alert_blocks: int):
    """
    Send an email notification.
    """

    message = EmailMessage()
    message['Subject'] = f"{domain} is expiring in {content['blocks']} blocks (~{content['time']})"
    message['From'] = f'FireAlerts <{SMTP_USERNAME}>'
    message['To'] = email_addr
    message.set_content(f"""
You set an alert for {domain}. This domain will expire in {content['blocks']} blocks or approximately {content['time']}.

Domain: {domain}
Blocks remaining: {content['blocks']}
Time remaining: {content['time']}
Alert threshold: {alert_blocks} blocks

Visit your FireAlerts account: https://alerts.firewallet.au/account/{domain}
""")

    try:
        print(f"Attempting to connect to {SMTP_SERVER}:{SMTP_PORT}")
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
            if SMTP_USERNAME and SMTP_PASSWORD:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(message)
        print(f"Email sent to {email_addr} for domain {domain}")
    except smtplib.SMTPException as e:
        print(f"SMTP error sending email to {email_addr}: {e}")
    except ConnectionRefusedError as e:
        print(
            f"Connection refused to SMTP server {SMTP_SERVER}:{SMTP_PORT} - {e}")
    except Exception as e:
        print(f"Unexpected error sending email to {email_addr}: {e}")
