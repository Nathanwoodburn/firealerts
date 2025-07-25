# FireAlerts

Get alerted before your Handshake domains expire.

## Overview

FireAlerts is a web application that monitors Handshake domain expiry dates and sends notifications when domains are approaching expiration. Users can set up multiple notification types including Discord webhooks and email alerts.

## Features

- Monitor multiple Handshake domains
- Multiple notification types (Discord webhook, Email)
- Customizable notification timing (blocks before expiry)
- User authentication via HNS.au login system
- REST API for programmatic access
- Background monitoring every 2 minutes

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment variables in `.env` using example.env as a template

3. Run the application:
```bash
python main.py
```

## API Documentation

### Authentication

Account API endpoints require a valid token from the HNS.au authentication system.

### Endpoints

#### Get Domain Information
```
GET /api/v1/domain/<domain>
```

Returns expiry information for a specific domain.

**Response:**
```json
{
  "domain": "example",
  "expiry_date": 123456,
  "expires_in_blocks": 1008
}
```

#### Get Current Block
```
GET /api/v1/current_block
```

Returns the current blockchain block number.

**Response:**
```json
{
  "current_block": 123456
}
```

#### Get User Notifications
```
GET /api/v1/notifications/<token>
```

Returns all notifications for the authenticated user.

**Response:**
```json
[
  {
    "domain": "example",
    "notification": {
      "type": "discord_webhook",
      "url": "https://discord.com/api/webhooks/...",
      "blocks": 1008,
      "id": "abc123",
      "user_name": "username"
    }
  }
]
```

#### Add Notification
```
POST /api/v1/notifications/<token>
```

Add a new notification for the authenticated user.

**Request Body:**
```json
{
  "domain": "example",
  "type": "discord_webhook",
  "url": "https://discord.com/api/webhooks/...",
  "blocks": 1008
}
```

**Response:**
```json
{
  "message": "Notification added successfully",
  "notification": {
    "type": "discord_webhook",
    "url": "https://discord.com/api/webhooks/...",
    "blocks": 1008,
    "id": "abc123",
    "user_name": "username"
  }
}
```

## Notification Types

### Discord Webhook
- **Type:** `discord_webhook`
- **Required Fields:**
  - `url`: Discord webhook URL

### Email
- **Type:** `email`
- **Required Fields:**
  - `email`: Email address

## Web Interface

### Routes

- `/` - Home page
- `/account` - User dashboard (requires authentication)
- `/login` - Authentication callback
- `/logout` - Clear authentication
- `/notification/<type>` - Add notification (POST)
- `/notification/delete/<id>` - Delete notification

## Background Processing

The application runs a background thread that checks domain expiries every 2 minutes. When a domain is within the specified number of blocks from expiry, appropriate notifications are sent.

## File Structure

- `server.py` - Main Flask application
- `domains.py` - Domain and notification management
- `alerts.py` - Notification handling and types
- `templates/` - HTML templates
- `templates/assets/` - Static assets (CSS, images)
- `data/domains.json` - Notification storage (created automatically)

## Dependencies

- Flask - Web framework
- requests - HTTP client
- python-dotenv - Environment variable management