from functools import cache
import json
from flask import (
    Flask,
    make_response,
    redirect,
    request,
    jsonify,
    render_template,
    send_from_directory,
    send_file,
)
import os
import json
import requests
from datetime import datetime
import dotenv
import threading
import time
import domains
import atexit
from alerts import NOTIFICATION_TYPES, startTGBot, stopTGBot, handle_alert

dotenv.load_dotenv()

app = Flask(__name__)

def run_expiry_checker():
    """
    Background function to run notify_expiries every 2 minutes.
    """
    while True:
        try:
            print("Running expiry check...")
            domains.notify_expiries()
            print("Expiry check completed.")
        except Exception as e:
            print(f"Error in expiry checker: {e}")
        
        # Wait 2 minutes (120 seconds)
        time.sleep(120)

def find(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)

# Assets routes
@app.route("/assets/<path:path>")
def send_assets(path):
    if path.endswith(".json"):
        return send_from_directory(
            "templates/assets", path, mimetype="application/json"
        )

    if os.path.isfile("templates/assets/" + path):
        return send_from_directory("templates/assets", path)

    # Try looking in one of the directories
    filename: str = path.split("/")[-1]
    if (
        filename.endswith(".png")
        or filename.endswith(".jpg")
        or filename.endswith(".jpeg")
        or filename.endswith(".svg")
    ):
        if os.path.isfile("templates/assets/img/" + filename):
            return send_from_directory("templates/assets/img", filename)
        if os.path.isfile("templates/assets/img/favicon/" + filename):
            return send_from_directory("templates/assets/img/favicon", filename)

    return render_template("404.html"), 404


# region Special routes
@app.route("/favicon.png")
def faviconPNG():
    return send_from_directory("templates/assets/img", "favicon.png")


@app.route("/.well-known/<path:path>")
def wellknown(path):
    # Try to proxy to https://nathan.woodburn.au/.well-known/
    req = requests.get(f"https://nathan.woodburn.au/.well-known/{path}")
    return make_response(
        req.content, 200, {"Content-Type": req.headers["Content-Type"]}
    )


# endregion


# region Main routes
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/account")
def account():
    # Check if the user is logged in
    # Check for token cookie
    token = request.cookies.get("token")
    if not token:
        return redirect(f"https://login.hns.au/auth?return={request.host_url}login")
    
    user_data = requests.get(f"https://login.hns.au/auth/user?token={token}")
    if user_data.status_code != 200:
        return redirect(f"https://login.hns.au/auth?return={request.host_url}login")
    user_data = user_data.json()

    notifications = domains.get_account_notifications(user_data["username"])
    if not notifications:
        return render_template("account.html", user=user_data, domains=[], NOTIFICATION_TYPES=NOTIFICATION_TYPES)


    return render_template("account.html", user=user_data, notifications=notifications, NOTIFICATION_TYPES=NOTIFICATION_TYPES)

@app.route("/login")
def login():
    # Check if token parameter is present
    token = request.args.get("token")
    if not token:
        return redirect(f"https://login.hns.au/auth?return={request.host_url}login")
    # Set token cookie
    response = make_response(redirect(f"{request.host_url}account"))
    response.set_cookie("token", token, httponly=True, secure=True)
    return response

@app.route("/logout")
def logout():
    # Clear the token cookie
    response = make_response(redirect(f"{request.host_url}"))
    response.set_cookie("token", "", expires=0, httponly=True, secure=True)
    return response


@app.route("/bulk_upload", methods=["POST"])
def bulk_upload_notifications():
    """
    Bulk upload notifications from a CSV file.
    """
    token = request.cookies.get("token")
    if not token:
        return redirect(f"https://login.hns.au/auth?return={request.host_url}login")
    
    user_data = requests.get(f"https://login.hns.au/auth/user?token={token}")
    if user_data.status_code != 200:
        return redirect(f"https://login.hns.au/auth?return={request.host_url}login")
    user_data = user_data.json()
    
    username = user_data.get("username", None)
    if not username:
        return jsonify({"error": "Invalid user data"}), 400

    # Check if the request contains a file
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    # Read the CSV file
    try:
        content = file.read().decode('utf-8')
        lines = content.splitlines()
        for line in lines:
            parts = line.split(',')
            if len(parts) < 3:
                continue  # Skip invalid lines
            
            domain = parts[0].strip()
            blocks = parts[1].strip()
            try:
                blocks = int(blocks)
                if blocks <= 0:
                    return jsonify({"error": "Blocks must be a positive integer"}), 400
            except ValueError:
                return jsonify({"error": "Invalid blocks value"}), 400

            notification_type = parts[2].strip().lower() # Normalize to lowercase

            # Find the notification type
            notificationType = None
            for notification in NOTIFICATION_TYPES:
                if notification['type'] == notification_type:
                    notificationType = notification
                    break
            else:
                return jsonify({"error": f"Invalid notification type: {notification_type}"}), 400
                continue  # Skip invalid notification types
            

            # Create the notification data
            notification_data = {
                'domain': domain,
                'blocks': blocks,
                'type': notification_type,
                'user_name': username,
                'id': os.urandom(16).hex()  # Generate a random ID for the notification
            }
            
            arg = 3
            # Add additional fields based on the notification type
            for field in notificationType['fields']:
                if field['name'] not in notification_data and field.get('required', False):
                    # Try to read the field from the line
                    if len(parts) > arg:
                        field_value = parts[arg].strip()
                        if field_value:
                            notification_data[field['name']] = field_value
                        else:
                            return jsonify({"error": f"Missing required field: {field['name']}"}), 400
                    else:
                        # Auto fill default values for username
                        if field['type'] == 'username':
                            notification_data[field['name']] = username
                        else:
                            return jsonify({"error": f"Missing required field: {field['name']}"}), 400
            print(notification_data)
            domains.add_notification(domain, notification_data)
        
        return redirect(f"{request.host_url}account")
    except Exception as e:
        return jsonify({"error": f"Failed to process file: {str(e)}"}), 500

@app.route("/notification/<notificationtype>", methods=["POST"])
def addNotification(notificationtype: str):
    """
    Add a notification for a domain.
    """

    token = request.cookies.get("token")
    if not token:
        return redirect(f"https://login.hns.au/auth?return={request.host_url}login")
    
    user_data = requests.get(f"https://login.hns.au/auth/user?token={token}")
    if user_data.status_code != 200:
        return redirect(f"https://login.hns.au/auth?return={request.host_url}login")
    user_data = user_data.json()
    username = user_data.get("username", None)
    if not username:
        return jsonify({"error": "Invalid user data"}), 400

    notificationType = None
    for notification in NOTIFICATION_TYPES:
        if notification['type'] == notificationtype:
            notificationType = notification
            break
    else:
        return jsonify({"error": "Invalid notification type"}), 400

    # Get form data
    data = request.form.to_dict()
    if not data or 'domain' not in data or 'blocks' not in data:
        return jsonify({"error": "Invalid request data"}), 400
    
    domain = data['domain']

    for field in notificationType['fields']:
        if field['name'] not in data and field.get('required', False):
            return jsonify({"error": f"Missing field: {field['name']}"}), 400


    notification = data

    # Convert blocks to integer
    try:
        blocks = int(notification['blocks'])
        if blocks <= 0:
            return jsonify({"error": "Blocks must be a positive integer"}), 400
    except ValueError:
        return jsonify({"error": "Invalid blocks value"}), 400

    notification['blocks'] = blocks # type: ignore
    notification['type'] = notificationtype
    notification['id'] = os.urandom(16).hex()  # Generate a random ID for the notification
    notification['user_name'] = username
    # Delete domain duplicate from data
    notification.pop('domain', None)

    domains.add_notification(domain, notification)
    return redirect(f"{request.host_url}account")

@app.route("/notification/delete/<notification_id>")
def delete_notification(notification_id: str):
    """
    Delete a notification by its ID.
    """
    token = request.cookies.get("token")
    if not token:
        return redirect(f"https://login.hns.au/auth?return={request.host_url}login")
    
    user_data = requests.get(f"https://login.hns.au/auth/user?token={token}")
    if user_data.status_code != 200:
        return redirect(f"https://login.hns.au/auth?return={request.host_url}login")
    user_data = user_data.json()
    
    domains.delete_notification(notification_id, user_data['username'])
    return redirect(f"{request.host_url}account")

@app.route("/telegram/link")
def telegram_link():
    """
    Redirect to Telegram login.
    """
    token = request.cookies.get("token")
    if not token:
        return redirect(f"https://login.hns.au/auth?return={request.host_url}login")
    
    TG_NAME = os.getenv("TELEGRAM_BOT", None)
    if not TG_NAME:
        return jsonify({"error": "Telegram bot name not configured"}), 500

    return redirect(f"https://t.me/{TG_NAME}?start={token}")

@app.route("/account/<domain>")
def account_domain(domain: str):
    # TODO - Implement account domain logic
    return redirect(f"/account")


@app.route("/<path:path>")
def catch_all(path: str):
    if os.path.isfile("templates/" + path):
        return render_template(path)

    # Try with .html
    if os.path.isfile("templates/" + path + ".html"):
        return render_template(path + ".html")

    if os.path.isfile("templates/" + path.strip("/") + ".html"):
        return render_template(path.strip("/") + ".html")

    # Try to find a file matching
    if path.count("/") < 1:
        # Try to find a file matching
        filename = find(path, "templates")
        if filename:
            return send_file(filename)

    return render_template("404.html"), 404

# endregion

# region API routes
@app.route("/api/v1/domain/<domain>")
def api_get_domain(domain: str):
    """
    Get the expiry date of a domain.
    """
    expiry_date = domains.get_domain_expiry_block(domain)
    current_block = domains.get_current_block()
    expires_in_blocks = expiry_date - current_block if expiry_date != -1 else -1
    
    return jsonify({"domain": domain, "expiry_date": expiry_date, "expires_in_blocks": expires_in_blocks})

@app.route("/api/v1/current_block")
def api_get_current_block():
    """
    Get the current block number.
    """
    current_block = domains.get_current_block()
    
    return jsonify({"current_block": current_block})

@app.route("/api/v1/notifications/<token>")
def api_get_notifications(token: str):
    """
    Get all notifications for a user.
    """
    user_data = requests.get(f"https://login.hns.au/auth/user?token={token}")
    if user_data.status_code != 200:
        return jsonify({"error": "Invalid token"}), 401
    user_data = user_data.json()
    
    notifications = domains.get_account_notifications(user_data["username"])
    
    return jsonify(notifications)

@app.route("/api/v1/notifications/<token>", methods=["POST"])
def api_add_notification(token: str):
    """
    Add a notification for a user.
    """
    user_data = requests.get(f"https://login.hns.au/auth/user?token={token}")
    if user_data.status_code != 200:
        return jsonify({"error": "Invalid token"}), 401
    user_data = user_data.json()
    
    username = user_data.get("username", None)
    if not username:
        return jsonify({"error": "Invalid user data"}), 400

    data = request.json
    if not data or 'domain' not in data or 'blocks' not in data or 'type' not in data:
        return jsonify({"error": "Invalid request data"}), 400
    
    domain = data['domain']
    
    notificationtype = data['type']
    notificationType = None
    for notification in NOTIFICATION_TYPES:
        if notification['type'] == notificationtype:
            notificationType = notification
            break
    else:
        return jsonify({"error": "Invalid notification type"}), 400
    
    for field in notificationType['fields']:
        if field['name'] not in data and field.get('required', False):
            return jsonify({"error": f"Missing field: {field['name']}"}), 400
    # Validate blocks
    try:
        blocks = int(data['blocks'])
        if blocks <= 0:
            return jsonify({"error": "Blocks must be a positive integer"}), 400
    except ValueError:
        return jsonify({"error": "Invalid blocks value"}), 400
    
    notification = data
    notification['blocks'] = blocks
    notification['type'] = notificationtype
    notification['id'] = os.urandom(16).hex()  # Generate a random ID for the notification
    notification['user_name'] = username
    # Delete domain duplicate from data
    notification.pop('domain', None)
    domains.add_notification(domain, notification)
    return jsonify({"message": "Notification added successfully", "notification": notification}), 201

# endregion

# region Error Catching
# 404 catch all
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


# endregion
if __name__ == "__main__":
    # Start the background expiry checker for development mode
    expiry_thread = threading.Thread(target=run_expiry_checker, daemon=True)
    expiry_thread.start()
    print("Started background expiry checker thread")
    
    # Start the Telegram bot in a separate thread (only in main process)
    startTGBot()
    
    # Register cleanup function
    atexit.register(stopTGBot)
    
    app.run(debug=True, port=5000, host="127.0.0.1")
