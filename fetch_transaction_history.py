"""
fetch_transaction_history.py

Fetches your completed buy/sell transaction history from GW2 API
and saves it to CSV files with proper timestamps.

Usage:
1. Make sure your .env file has GW2_KEY set
2. Run: python fetch_transaction_history.py
3. Gets you dated CSV files in data/buy_orders and data/sell_orders
"""

import requests
import csv
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

API_KEY = os.getenv('GW2_KEY')
if not API_KEY:
    raise RuntimeError('GW2_KEY not set in .env file')

BASE_URL = 'https://api.guildwars2.com/v2'
HEADERS = {'Authorization': f'Bearer {API_KEY}'}


def fetch_transaction_history(transaction_type):
    """
    Fetch completed transactions from GW2 API.
    transaction_type: 'buys' or 'sells'
    """
    url = f'{BASE_URL}/commerce/transactions/history/{transaction_type}'
    response = requests.get(url, headers=HEADERS, timeout=10)
    response.raise_for_status()
    return response.json()


def fetch_item_names(item_ids):
    """
    Bulk fetch item names from GW2 API.
    """
    names = {}
    ids = list(item_ids)
    
    # API allows max 200 IDs per request
    for i in range(0, len(ids), 200):
        chunk = ids[i:i+200]
        ids_str = ','.join(map(str, chunk))
        url = f'{BASE_URL}/items?ids={ids_str}'
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        for item in response.json():
            names[item['id']] = item['name']
    
    return names


def save_to_csv(transactions, filename):
    """
    Saves transactions to CSV with proper formatting.
    """
    if not transactions:
        print(f"No transactions to save for {filename}")
        return
    
    # Get unique item IDs and fetch names
    item_ids = set(t['item_id'] for t in transactions)
    item_names = fetch_item_names(item_ids)
    
    # Write to CSV
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'item_id',
            'item_name',
            'quantity',
            'price_copper',
            'created',
            'purchased',
            'time_to_fill_hours'
        ])
        
        for tx in transactions:
            created = datetime.fromisoformat(tx['created'].replace('Z', '+00:00'))
            purchased = datetime.fromisoformat(tx['purchased'].replace('Z', '+00:00'))
            time_to_fill = (purchased - created).total_seconds() / 3600  # hours
            
            writer.writerow([
                tx['item_id'],
                item_names.get(tx['item_id'], f"Unknown #{tx['item_id']}"),
                tx['quantity'],
                tx['price'],
                tx['created'],
                tx['purchased'],
                round(time_to_fill, 2)
            ])
    
    print(f"Saved {len(transactions)} transactions to {filename}")


def main():
    # Create data directories if they don't exist
    os.makedirs('data/buy_orders', exist_ok=True)
    os.makedirs('data/sell_orders', exist_ok=True)
    
    # Generate filename with today's date
    today = datetime.now().date()
    date_str = str(today)
    
    print("Fetching buy history...")
    buy_history = fetch_transaction_history('buys')
    buy_filepath = f'data/buy_orders/buy_history_{date_str}.csv'
    save_to_csv(buy_history, buy_filepath)
    
    print("\nFetching sell history...")
    sell_history = fetch_transaction_history('sells')
    sell_filepath = f'data/sell_orders/sell_history_{date_str}.csv'
    save_to_csv(sell_history, sell_filepath)
    
    print("\nDone! You now have:")
    print(f"  - {buy_filepath}")
    print(f"  - {sell_filepath}")
    print("\nThese files contain  last 50 completed transactions per type")
    print("with timestamps showing when orders were placed and when they filled.")
    print("\nRun this daily to accumulate historical data!")


if __name__ == '__main__':
    main()