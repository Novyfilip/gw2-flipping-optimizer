"""
app.py (complete)
Dependencies: flask, requests, python-dotenv

A Flask dashboard that shows:
- Open buy/sell orders
- Delivery box summary
- Medal-based G/S/C formatting
- Daily snapshot sparklines & volume history
- Favorites stub and volume API
"""
from flask import Flask, render_template, request, jsonify
import os, requests, sqlite3
from dotenv import load_dotenv
from datetime import date

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
# Record order state changes into order_events table
def update_order_events(buys, sells):
    conn = sqlite3.connect('tp.sqlite')
    c = conn.cursor()

    # Create order_events table
    c.execute(
        '''
        CREATE TABLE IF NOT EXISTS order_events (
            event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id   INTEGER,
            item_id    INTEGER NOT NULL,
            event_type TEXT    NOT NULL CHECK(event_type IN ('placed','filled','canceled','relisted')),
            quantity   INTEGER NOT NULL,
            price      INTEGER NOT NULL,
            fee        INTEGER,
            timestamp  TEXT    DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )

    # Current open orders tagged with side
    current = {o['id']: {**o, 'side': 'buy'} for o in buys}
    current.update({o['id']: {**o, 'side': 'sell'} for o in sells})
    current_ids = set(current)

    # Previously placed orders without a terminal event
    c.execute(
        '''
        SELECT order_id, item_id, quantity, price
        FROM order_events oe
        WHERE event_type = 'placed'
        AND NOT EXISTS (
            SELECT 1 FROM order_events oe2
            WHERE oe2.order_id = oe.order_id AND oe2.event_type != 'placed'
        )
        '''
    )
    active = {row[0]: {'item_id': row[1], 'quantity': row[2], 'price': row[3]} for row in c.fetchall()}

    # Insert placed events for new orders
    for oid, order in current.items():
        if oid not in active:
            fee = int(order['price'] * order['quantity'] * 0.05) if order['side'] == 'sell' else 0
            c.execute(
                '''
                INSERT INTO order_events (order_id, item_id, event_type, quantity, price, fee)
                VALUES (?, ?, 'placed', ?, ?, ?)
                ''',
                (oid, order['item_id'], order['quantity'], order['price'], fee)
            )

    # Determine orders that changed state
    missing = set(active) - current_ids
    canceled_info = []
    if missing:
        history_map = {}
        for h in gw2_get('commerce/transactions/history/buys'):
            history_map[h['id']] = (h, 'buy')
        for h in gw2_get('commerce/transactions/history/sells'):
            history_map[h['id']] = (h, 'sell')
        for oid in missing:
            prev = active[oid]
            if oid in history_map:
                h, side = history_map[oid]
                fee = int(h['price'] * h['quantity'] * 0.10) if side == 'sell' else 0
                c.execute(
                    '''
                    INSERT INTO order_events (order_id, item_id, event_type, quantity, price, fee)
                    VALUES (?, ?, 'filled', ?, ?, ?)
                    ''',
                    (oid, h['item_id'], h['quantity'], h['price'], fee)
                )
            else:
                c.execute(
                    '''
                    INSERT INTO order_events (order_id, item_id, event_type, quantity, price)
                    VALUES (?, ?, 'canceled', ?, ?)
                    ''',
                    (oid, prev['item_id'], prev['quantity'], prev['price'])
                )
                canceled_info.append((oid, prev))

    # Match canceled orders to new ones for relist detection
    new_ids = current_ids - set(active)
    by_item_qty = {}
    for oid in new_ids:
        o = current[oid]
        key = (o['item_id'], o['quantity'])
        by_item_qty.setdefault(key, []).append((oid, o))

    for old_oid, prev in canceled_info:
        key = (prev['item_id'], prev['quantity'])
        lst = by_item_qty.get(key)
        if lst:
            new_oid, new_order = lst.pop(0)
            fee = int(new_order['price'] * new_order['quantity'] * 0.05) if new_order['side'] == 'sell' else 0
            c.execute(
                '''
                INSERT INTO order_events (order_id, item_id, event_type, quantity, price, fee)
                VALUES (?, ?, 'relisted', ?, ?, ?)
                ''',
                (old_oid, prev['item_id'], new_order['quantity'], new_order['price'], fee)
            )

    conn.commit()
    conn.close()

# Fetch open buy/sell orders
def fetch_orders():
    buys  = gw2_get('commerce/transactions/current/buys')
    sells = gw2_get('commerce/transactions/current/sells')
    update_order_events(buys, sells)
    return buys, sells
    
# Fetch delivery box summary
def fetch_deliveries():
    return gw2_get('commerce/delivery')

# Bulk lookup item names via /v2/items
def fetch_names(item_ids):
    names = {}
    ids   = list(item_ids)
    for i in range(0, len(ids), 200):
        chunk = ids[i:i+200]
        data  = gw2_get(f"items?ids={','.join(map(str,chunk))}")
        for entry in data:
            names[entry['id']] = entry['name']
    return names

# Upsert daily gold snapshot and item volumes
def upsert_snapshot(grand_copper, item_ids):
    conn = sqlite3.connect('tp.sqlite')
    c = conn.cursor()

    # daily_snapshots table
    c.execute('''
      CREATE TABLE IF NOT EXISTS daily_snapshots (
          snapshot_date TEXT PRIMARY KEY,
          grand_copper   INTEGER NOT NULL
      )
    ''')

    today = date.today().isoformat()
    c.execute("""
      INSERT INTO daily_snapshots (snapshot_date, grand_copper)
      VALUES (?, ?)
      ON CONFLICT(snapshot_date) DO UPDATE
        SET grand_copper=excluded.grand_copper
    """, (today, grand_copper))

    # daily_item_volume table
    c.execute('''
      CREATE TABLE IF NOT EXISTS daily_item_volume (
          item_id       INTEGER,
          snapshot_date TEXT,
          volume        INTEGER,
          PRIMARY KEY(item_id, snapshot_date)
      )
    ''')

    # fetch current 24 h volumes for those items
    if item_ids:
        ids_str = ','.join(map(str, item_ids))
        prices = gw2_get(f"commerce/prices?ids={ids_str}")
        for entry in prices:
            vid = entry['id']
            vol = entry.get('volume', 0)
            c.execute("""
              INSERT INTO daily_item_volume (item_id, snapshot_date, volume)
              VALUES (?, ?, ?)
              ON CONFLICT(item_id, snapshot_date) DO UPDATE
                SET volume=excluded.volume
            """, (vid, today, vol))

    conn.commit()
    conn.close()

@app.route('/')
def index():
    # Pull raw data
    raw_buys, raw_sells   = fetch_orders()
    delivery_data         = fetch_deliveries()
    coins                 = delivery_data.get('coins', 0)
    raw_deliveries_items  = delivery_data.get('items', [])

    # Compute totals in copper
    total_buy_copper      = sum(o['price'] * o['quantity'] for o in raw_buys)
    total_sell_copper     = sum(o['price'] * o['quantity'] for o in raw_sells)
    total_delivery_copper = coins + sum(
        d.get('unit_price', d.get('price', 0))
        * d.get('count',  d.get('quantity', 0))
        for d in raw_deliveries_items
    )
    grand_total_copper    = (
        total_buy_copper
      + total_sell_copper
      + total_delivery_copper
    )

    # Collect all item IDs
    ids = {o['item_id'] for o in raw_buys} | {o['item_id'] for o in raw_sells}
    ids |= {d.get('item_id', d.get('id')) for d in raw_deliveries_items}
    delivery_ids = {
        d.get('item_id') or d.get('id')
        for d in raw_deliveries_items
        if d.get('item_id') or d.get('id')
    }
    ids |= delivery_ids

    # Save daily snapshots and volumes
    upsert_snapshot(grand_total_copper, ids)

    # Load last 7 days for sparkline
    conn = sqlite3.connect('tp.sqlite')
    c = conn.cursor()
    c.execute("""
      SELECT snapshot_date, grand_copper/10000.0
      FROM daily_snapshots
      ORDER BY snapshot_date DESC
      LIMIT 7
    """
    )
    rows = c.fetchall()
    conn.close()
    dates, values = (zip(*rows[::-1]) if rows else ([], []))

    # Name mapping
    name_map = fetch_names(ids)

    # Build lists
    buys = [
        {'name': name_map.get(o['item_id'], f"#{o['item_id']}"),
         'quantity': o['quantity'], 'price': o['price']}
        for o in raw_buys
    ]
    sells = [
        {'name': name_map.get(o['item_id'], f"#{o['item_id']}"),
         'quantity': o['quantity'], 'price': o['price']}
        for o in raw_sells
    ]
    deliveries = [
        {'name': name_map.get(d.get('item_id', d.get('id')), f"#{d.get('item_id', d.get('id'))}"),
         'quantity': d.get('count', d.get('quantity', 0)),
         'price':    d.get('unit_price', d.get('price', 0))}
        for d in raw_deliveries_items
    ]

    # Prepare totals for chart
    totals = {
        'Buy':      total_buy_copper/10000,
        'Sell':     total_sell_copper/10000,
        'Delivery': total_delivery_copper/10000,
        'Grand':    grand_total_copper/10000,
    }

    # Render template with all data
    return render_template(
        'index.html',
        buys=buys,
        sells=sells,
        deliveries=deliveries,
        total_buy_copper=total_buy_copper,
        total_sell_copper=total_sell_copper,
        total_delivery_copper=total_delivery_copper,
        grand_total_copper=grand_total_copper,
        dates=list(dates),
        values=list(values),
        totals=totals
    )

@app.route('/favorites')
def favorites():
    return render_template('favorites.html')

# Item-search API stub
@app.route('/api/items/search')
def api_search_items():
    q = request.args.get('q', '').lower()
    all_items = [
        {'id': 80,    'name': "Nika's Mask"},
        {'id': 714,   'name': "Reclaimed Warhorn"},
        {'id': 97284, 'name': "Jade Bot Core: Tier 3"},
    ]
    results = [itm for itm in all_items if q in itm['name'].lower()]
    return jsonify(results)

# Volume-history API
@app.route('/api/volume')
def api_volume():
    ids = request.args.get('ids','').split(',')
    conn = sqlite3.connect('tp.sqlite')
    c = conn.cursor()
    placeholders = ','.join('?' for _ in ids)
    q = f"""
      SELECT item_id, snapshot_date, volume
      FROM daily_item_volume
      WHERE item_id IN ({placeholders})
      ORDER BY item_id, snapshot_date DESC
      LIMIT 7
    """
    rows = c.execute(q, ids).fetchall()
    conn.close()
    out = {}
    for item_id, dt, vol in rows:
        out.setdefault(item_id, []).append({'date': dt, 'volume': vol})
    for lst in out.values():
        lst.reverse()
    return jsonify(out)

if __name__ == '__main__':
    app.run(debug=True)