"""
app.py (complete)
Dependencies: flask, requests, python-dotenv

A Flask dashboard that shows:
- Open buy/sell orders
- Delivery box summary
- Medal-based G/S/C formatting

Setup:
  pip install flask requests python-dotenv
  cp .env.example .env        # add GW2_KEY=...
  python app.py
Visit http://127.0.0.1:5000/
"""
from flask import Flask, render_template
import os, requests
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Build auth header for GW2 API
def auth_header():
    key = os.getenv('GW2_KEY')
    if not key:
        raise RuntimeError('GW2_KEY not set in environment')
    return {'Authorization': f'Bearer {key}'}

BASE = 'https://api.guildwars2.com/v2'
app  = Flask(__name__)

# Generic GET helper
def gw2_get(path: str):
    url  = f"{BASE}/{path}"
    resp = requests.get(url, headers=auth_header(), timeout=10)
    resp.raise_for_status()
    return resp.json()

# 1) Fetch open buy/sell orders
def fetch_orders():
    buys  = gw2_get('commerce/transactions/current/buys')
    sells = gw2_get('commerce/transactions/current/sells')
    return buys, sells

# 2) Fetch delivery box summary
def fetch_deliveries():
    # returns { 'coins': int, 'items': [ {id,count,unit_price,...}, ... ] }
    return gw2_get('commerce/delivery')

# 3) Bulk lookup item names via /v2/items
def fetch_names(item_ids):
    names = {}
    ids   = list(item_ids)
    for i in range(0, len(ids), 200):
        chunk = ids[i:i+200]
        data  = gw2_get(f"items?ids={','.join(map(str,chunk))}")
        for entry in data:
            names[entry['id']] = entry['name']
    return names

@app.route('/')
def index():
    # Pull raw data
    raw_buys, raw_sells   = fetch_orders()
    delivery_data         = fetch_deliveries()
    coins                 = delivery_data.get('coins', 0)
    raw_deliveries_items  = delivery_data.get('items', [])

    # Totals in copper
    total_buy_copper      = sum(o['price'] * o['quantity'] for o in raw_buys)
    total_sell_copper     = sum(o['price'] * o['quantity'] for o in raw_sells)
    total_delivery_copper = coins + sum(
        d.get('unit_price', d.get('price', 0))
        * d.get('count',  d.get('quantity', 0))
        for d in raw_deliveries_items
    )

    # Grand total
    grand_total_copper    = (
        total_buy_copper
      + total_sell_copper
      + total_delivery_copper
    )

    # Collect all item IDs for naming
    ids = {o['item_id'] for o in raw_buys} | {o['item_id'] for o in raw_sells}
    ids |= {d.get('item_id', d.get('id')) for d in raw_deliveries_items}
    name_map = fetch_names(ids)

    # Build list of buys
    buys = []
    for o in raw_buys:
        buys.append({
            'name':     name_map.get(o['item_id'], f"#{o['item_id']}"),
            'quantity': o['quantity'],
            'price':    o['price'],
        })

    # Build list of sells
    sells = []
    for o in raw_sells:
        sells.append({
            'name':     name_map.get(o['item_id'], f"#{o['item_id']}"),
            'quantity': o['quantity'],
            'price':    o['price'],
        })

    # Build list of delivery items
    deliveries = []
    for d in raw_deliveries_items:
        deliveries.append({
            'name':     name_map.get(d.get('item_id', d.get('id')), f"#{d.get('item_id', d.get('id'))}"),
            'quantity': d.get('count', d.get('quantity', 0)),
            'price':    d.get('unit_price', d.get('price', 0)),
        })

    # Render template with all data
    return render_template(
        'index.html',
        buys=buys,
        sells=sells,
        deliveries=deliveries,
        total_buy_copper=total_buy_copper,
        total_sell_copper=total_sell_copper,
        total_delivery_copper=total_delivery_copper,
        grand_total_copper=grand_total_copper
    )

if __name__ == '__main__':
    app.run(debug=True)
