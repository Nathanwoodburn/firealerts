import json
import os
import requests
import smtplib
from email.message import EmailMessage
from email.mime.text import MIMEText
from email.headerregistry import Address
import ssl
import dotenv
import asyncio
import threading
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

dotenv.load_dotenv()

SMTP_SERVER = os.getenv('SMTP_SERVER', 'localhost')
SMTP_PORT = int(os.getenv('SMTP_PORT', 465))
SMTP_USERNAME = os.getenv('SMTP_USERNAME', None)
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', None)

TG_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', None)
TG_BOT_NAME = os.getenv('TELEGRAM_BOT', None)
TG_app = None
TG_bot_running = False


NOTIFICATION_TYPES = [
    {
        "type": "discord_webhook",
        "fields": [
            {
                "name": "url",
                "label": "Discord Webhook URL",
                "type": "text",
                "required": True
            }
        ],
        "description": "Send a notification to a Discord channel via webhook."
    },
    {
        "type": "email",
        "fields": [
            {
                "name": "email",
                "label": "Email Address",
                "type": "email",
                "required": True
            }
        ],
        "description": "Send an email notification."
    },
    {
        "type": "telegram",
        "fields": [
            {
                "name": "username",
                "label": "Username",
                "type": "username",
                "required": True
            }
        ],
        "description": "Send a telegram notification.",
        "links": [
            {
                "label": "Link your Telegram account",
                "url": "/telegram/link"
            }
        ]
    }
]


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
    elif alert_type == 'telegram':
        telegram(notification['username'], domain,
                 alert_data, notification['blocks'])
    else:
        print(f"Unknown alert type: {alert_type} for domain: {domain}")


def discord_webhook(webhook_url: str, domain: str, content: dict, alert_blocks: int):
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


async def link_tg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Try to read a token
    if not update.message or not update.message.text:
        print("No message text found in update.")
        return

    # Check to make sure that the message is in format /start <token>
    if not update.message.text.startswith('/start '):
        await update.message.reply_markdown_v2("Please link your Telegram account from [FireAlerts](https://alerts.firewallet.au/telegram/link)")
        return

    token = update.message.text.split(' ', 1)[1].strip()
    if not token:
        await update.message.reply_text("Please provide a valid token.")
        return

    # Try to validate the token
    user_data = requests.get(f"https://login.hns.au/auth/user?token={token}")
    if user_data.status_code != 200:
        await update.message.reply_text("Invalid token. Please try again.")
        return
    user_data = user_data.json()
    user_name = user_data.get('username')
    if not user_name:
        await update.message.reply_text("Invalid token. Please try again.")
        return

    if not os.path.exists('data'):
        os.makedirs('data')
    if not os.path.exists('data/telegram.json'):
        with open('data/telegram.json', 'w') as f:
            json.dump({}, f)

    # Load existing Telegram data
    with open('data/telegram.json', 'r') as f:
        telegram_data = json.load(f)

    if not update.message.from_user:
        await update.message.reply_text("Could not retrieve your Telegram user information.")
        return
    # Update or add the user
    telegram_data[user_name] = {
        "user_id": update.message.from_user.id,
        "username": update.message.from_user.username
    }

    # Save the updated data
    with open('data/telegram.json', 'w') as f:
        json.dump(telegram_data, f, indent=4)

    await update.message.reply_text(f'You have linked your Telegram account with username: {user_name}. You will now receive notifications for your domains.')


async def ping_tg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        print("No message or user found in update.")
        return
    await update.message.reply_text(f"Pong!")

async def help_tg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        print("No message or user found in update.")
        return
    help_text = (
        "Welcome to FireAlerts Telegram Bot!\n\n"
        "Here are the commands you can use:\n"
        "/start - Link your Telegram account with FireAlerts.\n"
        "/ping - Check if the bot is running.\n"
        "/help - Show this help message."
    )
    await update.message.reply_text(help_text)


def startTGBot(mainThread: bool = False):
    """
    Start the Telegram bot in a separate thread.
    """
    global TG_bot_running

    if not TG_BOT_TOKEN or not TG_BOT_NAME:
        print(
            "Telegram bot token or name not set. Notifications via Telegram will not work.")
        return

    if TG_bot_running:
        print("Telegram bot is already running.")
        return

    # Check if this is the Flask reloader process (only skip if not main thread)
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true' and not mainThread:
        print("Skipping Telegram bot start in Flask reloader process.")
        return

    def run_bot():
        """Run the bot in a separate thread with its own event loop."""
        global TG_bot_running
        TG_bot_running = True
        loop = None

        try:
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            global TG_app
            if TG_app is None:
                if not TG_BOT_TOKEN:
                    print("Telegram bot token is not set. Cannot start bot.")
                    return

                TG_app = ApplicationBuilder().token(TG_BOT_TOKEN).build()

            TG_app.add_handler(CommandHandler("start", link_tg))
            TG_app.add_handler(CommandHandler("ping", ping_tg))
            TG_app.add_handler(CommandHandler("help", help_tg))
            print("Starting Telegram bot...")

            # Use start_polling and idle instead of run_polling
            async def start_bot():
                if not TG_app:
                    print("Telegram app is not initialized. Cannot start bot.")
                    return
                
                retry_count = 0
                max_retries = 5
                
                while TG_bot_running and retry_count < max_retries:
                    try:
                        await TG_app.initialize()
                        await TG_app.start()
                        if not TG_app.updater:
                            print("Telegram app updater is not initialized. Cannot start bot.")
                            return
                        
                        # Start polling with error handling
                        await TG_app.updater.start_polling(
                            drop_pending_updates=True,
                            allowed_updates=["message"],
                            timeout=30
                        )
                        print("Telegram bot is now running...")
                        retry_count = 0  # Reset retry count on successful start
                        
                        # Keep the bot running
                        while TG_bot_running:
                            await asyncio.sleep(1)
                            
                    except Exception as e:
                        print(f"Telegram bot error (attempt {retry_count + 1}/{max_retries}): {e}")
                        retry_count += 1
                        
                        if retry_count < max_retries and TG_bot_running:
                            wait_time = min(2 ** retry_count, 60)  # Exponential backoff, max 60 seconds
                            print(f"Retrying in {wait_time} seconds...")
                            await asyncio.sleep(wait_time)
                        else:
                            print("Max retries reached or bot stopped. Exiting.")
                            break
                    
                    finally:
                        try:
                            if TG_app:
                                await TG_app.stop()
                                await TG_app.shutdown()
                        except Exception as e:
                            print(f"Error stopping Telegram app: {e}")

            # Run the bot
            loop.run_until_complete(start_bot())

        except Exception as e:
            print(f"Error running Telegram bot: {e}")
        finally:
            TG_bot_running = False
            try:                
                if loop and not loop.is_closed():
                    loop.close()
            except Exception as e:
                print(f"Error closing event loop: {e}")

    # Start the bot in a daemon thread so it doesn't prevent the main program from exiting
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    print("Telegram bot started in background thread")


def stopTGBot():
    """
    Stop the Telegram bot.
    """
    global TG_bot_running
    TG_bot_running = False
    print("Stopping Telegram bot...")


def telegram(username: str, domain: str, content: dict, alert_blocks: int):
    """
    Send a Telegram notification.
    """
    # Load Telegram user data
    if not os.path.exists('data/telegram.json'):
        print(
            f"No Telegram data file found. Cannot send notification to {username}")
        return

    try:
        with open('data/telegram.json', 'r') as f:
            telegram_data = json.load(f)
    except Exception as e:
        print(f"Error reading Telegram data: {e}")
        return

    if username not in telegram_data:
        print(
            f"Username {username} not found in Telegram data. User needs to link their account.")
        return

    user_id = telegram_data[username].get('user_id')
    if not user_id:
        print(f"No user_id found for username {username}")
        return

    # Create the message
    message = f"""🔥 *FireAlerts Notification*

Domain: `{domain}`
Expires in: *{content['blocks']} blocks* (~{content['time']})
Alert threshold: {alert_blocks} blocks

[Open your FireAlerts account](https://alerts.firewallet.au/account/{domain})"""

    # Send the message in a separate thread with its own bot instance
    def send_telegram_message():
        loop = None
        local_app = None
        try:
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def send_message():
                nonlocal local_app
                try:
                    if not TG_BOT_TOKEN:
                        print("Telegram bot token is not set. Cannot send message.")
                        return
                    
                    # Create a new bot instance for this thread
                    local_app = ApplicationBuilder().token(TG_BOT_TOKEN).build()
                    await local_app.initialize()
                    
                    await local_app.bot.send_message(
                        chat_id=user_id,
                        text=message,
                        parse_mode='Markdown',
                        disable_web_page_preview=True
                    )
                    print(
                        f"Telegram notification sent to {username} (ID: {user_id}) for domain {domain}")
                except Exception as e:
                    print(f"Error sending Telegram message to {username}: {e}")
                finally:
                    if local_app:
                        try:
                            await local_app.shutdown()
                        except Exception as e:
                            print(f"Error shutting down local Telegram app: {e}")

            # Run the async function
            loop.run_until_complete(send_message())

        except Exception as e:
            print(f"Error in Telegram message thread: {e}")
        finally:
            try:
                if loop and not loop.is_closed():
                    loop.close()
            except Exception as e:
                print(f"Error closing Telegram message loop: {e}")

    # Start the message sending in a daemon thread
    message_thread = threading.Thread(
        target=send_telegram_message, daemon=True)
    message_thread.start()
