"""
fetch_transaction_history.py — Export completed buy/sell transactions from GW2 API.
Saves to data/buy_orders/ and data/sell_orders/ with item names and fill times.
"""
import requests, csv, os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

API_KEY = os.getenv('GW2_KEY')
if not API_KEY:
    raise RuntimeError('GW2_KEY not set in .env file')

BASE_URL = 'https://api.guildwars2.com/v2'
HEADERS = {'Authorization': f'Bearer {API_KEY}'}


def fetch_transaction_history(transaction_type):
    url = f'{BASE_URL}/commerce/transactions/history/{transaction_type}'
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_item_names(item_ids):
    names = {}
    ids = list(item_ids)
    for i in range(0, len(ids), 200):
        chunk = ids[i:i+200]
        url = f'{BASE_URL}/items?ids={",".join(map(str, chunk))}'
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        for item in resp.json():
            names[item['id']] = item['name']
    return names


def save_to_csv(transactions, filename):
    if not transactions:
        print(f"No transactions for {filename}")
        return
    item_ids = set(t['item_id'] for t in transactions)
    item_names = fetch_item_names(item_ids)
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['item_id', 'item_name', 'quantity', 'price_copper',
                          'created', 'purchased', 'time_to_fill_hours'])
        for tx in transactions:
            created = datetime.fromisoformat(tx['created'].replace('Z', '+00:00'))
            purchased = datetime.fromisoformat(tx['purchased'].replace('Z', '+00:00'))
            time_to_fill = (purchased - created).total_seconds() / 3600
            writer.writerow([tx['item_id'],
                item_names.get(tx['item_id'], f"Unknown #{tx['item_id']}"),
                tx['quantity'], tx['price'],
                tx['created'], tx['purchased'], round(time_to_fill, 2)])
    print(f"Saved {len(transactions)} transactions to {filename}")


def main():
    os.makedirs('data/buy_orders', exist_ok=True)
    os.makedirs('data/sell_orders', exist_ok=True)
    today = datetime.now().date().isoformat()
    print("Fetching buy history...")
    buy = fetch_transaction_history('buys')
    save_to_csv(buy, f'data/buy_orders/buy_history_{today}.csv')
    print("Fetching sell history...")
    sell = fetch_transaction_history('sells')
    save_to_csv(sell, f'data/sell_orders/sell_history_{today}.csv')
    print("Done.")


if __name__ == '__main__':
    main()
