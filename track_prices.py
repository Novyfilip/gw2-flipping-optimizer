"""
track_prices.py — Daily price snapshot for all tracked items.

Sources (union of):
  1. Items currently in open_orders (actively trading)
  2. Items from data/my_trading_items.csv (full catalog, always tracked)

Retries up to 3 times if GW2 API is unavailable.
"""
import sqlite3, requests, os, time, csv
from datetime import date
from dotenv import load_dotenv

load_dotenv()

BASE = 'https://api.guildwars2.com/v2'
HEADERS = {'Authorization': f"Bearer {os.getenv('GW2_KEY')}"}
DB = 'tp.sqlite'
MAX_RETRIES = 3


def get_known_items():
    """Union of open_orders items + catalog items."""
    item_ids = set()

    # Source 1: items currently in open orders
    try:
        conn = sqlite3.connect(DB)
        rows = conn.execute("SELECT DISTINCT item_id FROM open_orders").fetchall()
        conn.close()
        item_ids.update(r[0] for r in rows)
    except sqlite3.OperationalError:
        pass  # table doesn't exist yet

    # Source 2: full trading catalog
    try:
        with open('data/my_trading_items.csv', 'r') as f:
            reader = csv.DictReader(f)
            item_ids.update(int(row['item_id']) for row in reader)
    except FileNotFoundError:
        pass

    return sorted(item_ids)


def fetch_prices(item_ids):
    """Batch-fetch current buy/sell prices with retries."""
    prices = {}
    for i in range(0, len(item_ids), 200):
        chunk = item_ids[i:i + 200]
        ids_str = ','.join(map(str, chunk))

        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.get(
                    f'{BASE}/commerce/prices?ids={ids_str}',
                    headers=HEADERS, timeout=15)
                resp.raise_for_status()
                for entry in resp.json():
                    prices[entry['id']] = {
                        'buy_price':  entry['buys']['unit_price'],
                        'buy_qty':    entry['buys']['quantity'],
                        'sell_price': entry['sells']['unit_price'],
                        'sell_qty':   entry['sells']['quantity'],
                    }
                break
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(5 * (attempt + 1))
                else:
                    print(f"  Failed after {MAX_RETRIES} attempts: {e}")
    return prices


def ensure_table():
    conn = sqlite3.connect(DB)
    conn.execute('''CREATE TABLE IF NOT EXISTS item_prices (
        item_id    INTEGER, date TEXT,
        buy_price  INTEGER, buy_qty    INTEGER,
        sell_price INTEGER, sell_qty   INTEGER,
        PRIMARY KEY (item_id, date))''')
    conn.commit()
    conn.close()


def store_prices(prices):
    today = date.today().isoformat()
    conn = sqlite3.connect(DB)
    for item_id, p in prices.items():
        conn.execute('''INSERT OR REPLACE INTO item_prices
            (item_id, date, buy_price, buy_qty, sell_price, sell_qty)
            VALUES (?, ?, ?, ?, ?, ?)''',
            (item_id, today, p['buy_price'], p['buy_qty'],
             p['sell_price'], p['sell_qty']))
    conn.commit()
    conn.close()


def main():
    ensure_table()
    items = get_known_items()
    if not items:
        print("No items found. Run the dashboard first, or add data/my_trading_items.csv.")
        return
    print(f"Tracking {len(items)} items...")
    prices = fetch_prices(items)
    store_prices(prices)
    print(f"Saved prices for {len(prices)} items ({date.today().isoformat()}).")


if __name__ == '__main__':
    main()
