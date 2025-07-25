import json
import os
import requests
import dotenv
import alerts
dotenv.load_dotenv()

HSD_URL = os.getenv('HSD_URL', 'localhost')
HSD_API_KEY = os.getenv('HSD_API_KEY', None)
HSD_NETWORK = os.getenv('HSD_NETWORK', 'main')

HSD_PORTS = {
    'main': 12037,
    'testnet': 13037,
    'regtest': 14037,
    'simnet': 15037,
}
HSD_PORT = HSD_PORTS.get(HSD_NETWORK, 12037)

HSD_URL_FULL = f'http://x:{HSD_API_KEY}@{HSD_URL}:{HSD_PORT}' if HSD_API_KEY else f'http://{HSD_URL}:{HSD_PORT}'

if not os.path.exists('data'):
    os.makedirs('data')

if not os.path.exists('data/domains.json'):
    with open('data/domains.json', 'w') as f:
        json.dump({}, f)


def get_current_block() -> int:
    """
    Get the current block number from the HSD node.
    """
    response = requests.get(HSD_URL_FULL)
    
    if response.status_code != 200:
        print(f"Error fetching current block: {response.status_code} - {response.text}")
        return -1
    
    data = response.json()
    if 'error' in data and data['error'] is not None:
        print(f"Error fetching current block: {data['error']}")
        return -1
    
    chain_data = data.get('chain', None)
    if not chain_data or 'height' not in chain_data:
        print("No chain data or height found in response.")
        return -1
    return chain_data['height']

def get_domain_expiry_block(domain: str) -> int:
    """
    Get the expiry block of a domain.
    """
    response = requests.post(HSD_URL_FULL, json={ "method": "getnameinfo", "params":[domain] })
        
    if response.status_code != 200:
        return -1
    
    data = response.json()
    if 'error' in data and data['error'] is not None:
        print(f"Error fetching data for {domain}: {data['error']}")
        return -1

    if 'result' not in data or 'info' not in data['result']:
        print(f"No result or info found for {domain}.")
        return -1
    
    if 'stats' not in data['result']['info']:
        print(f"No stats information found for {domain}.")
        return -1
    
    stats = data['result']['info']['stats']
    if 'renewalPeriodEnd' not in stats:
        print(f"No renewalPeriodEnd found in stats for {domain}.")
        return -1

    return stats['renewalPeriodEnd']

def get_domains() -> dict:
    """
    Get the dict of domains from the JSON file.
    """
    with open('data/domains.json', 'r') as f:
        domains = json.load(f)
    return domains

def add_notification(domain: str, notification: dict):
    """
    Add a notification for a domain.
    """
    domains = get_domains()
    if domain not in domains:
        domains[domain] = []
    domains[domain].append(notification)
    
    with open('data/domains.json', 'w') as f:
        json.dump(domains, f, indent=4)

def update_notification(domain: str, notification: dict):
    """
    Update a notification for a domain.
    """
    domains = get_domains()
    if domain in domains:
        for i, existing_notification in enumerate(domains[domain]):
            if existing_notification['type'] == notification['type'] and existing_notification['id'] == notification['id']:
                domains[domain][i] = notification
                break
        else:
            domains[domain].append(notification)
    else:
        domains[domain] = [notification]
    
    with open('data/domains.json', 'w') as f:
        json.dump(domains, f, indent=4)

def delete_notification(notification_id: str, user_name: str):
    """
    Delete a notification for a domain.
    """
    domains = get_domains()
    domains_to_delete = []
    
    for domain in domains:
        domains[domain] = [n for n in domains[domain] if n['id'] != notification_id or n.get('user_name') != user_name]
        if not domains[domain]:
            domains_to_delete.append(domain)
    
    # Remove empty domains after iteration
    for domain in domains_to_delete:
        del domains[domain]
    
    with open('data/domains.json', 'w') as f:
        json.dump(domains, f, indent=4)

def get_account_notifications(user_name: str) -> list:
    """
    Get all notifications for a specific account.
    """
    domains = get_domains()
    # For each notification check if user_name
    notifications = []
    for domain, domain_notifications in domains.items():
        for notification in domain_notifications:
            if notification.get('user_name') == user_name:
                notifications.append({
                    'domain': domain,
                    'notification': notification
                })
    return notifications


def notify_expiries():
    """
    Notify about the expiry of domains.
    """
    domains = get_domains()
    if not domains:
        print("No domains found.")
        return
    current_block = get_current_block()


    for domain in domains:
        expiry_block = get_domain_expiry_block(domain)
        if expiry_block == -1:
            continue
        blocks_remaining = expiry_block - current_block
        domain_data = {
            "blocks": blocks_remaining,
            "time": f"{blocks_remaining // 144} days"  # Assuming 144 blocks per day
        }
        for notification in domains[domain]:
            if notification['blocks'] <= blocks_remaining and notification['blocks'] >= (blocks_remaining - 1): # Just in case there are 2 blocks really close together
                # Check if last block notified is more than current block + 5
                if notification.get('last_block_notified', -1) < (current_block - 5):
                    notification['last_block_notified'] = current_block
                    # Update the notification
                    update_notification(domain, notification)
                    # Handle the alert
                    alerts.handle_alert(domain, notification, domain_data)
            


if __name__ == "__main__":
    # Example usage
    domain = "woodburn"
    try:
        expiry = get_domain_expiry_block(domain)
        print(f"The expiry block for {domain} is: {expiry}")
    except Exception as e:
        print(f"Error fetching expiry for {domain}: {e}")

    # Notify about domain expiries
    notify_expiries()

    print(json.dumps(get_account_notifications('nathan'), indent=4))