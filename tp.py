"""
tp.py — GW2 Trading Post Dashboard + Recommender
Flask app with live orders, delivery box, gold tracking, and portfolio optimizer.
"""
from flask import Flask, render_template, request, session, redirect, url_for
from users import verify_user, create_user
import os, requests, sqlite3, json
from dotenv import load_dotenv
from datetime import date
from db import ensure_tables
from orders import persist_current_orders
from optimizer import optimize as run_optimizer
from models import load_models
import pandas as pd

load_dotenv()
ensure_tables()

USER_ID = int(os.getenv('TP_USER_ID', '1'))
BASE = 'https://api.guildwars2.com/v2'
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "dev-secret")


def auth_header():
    key = os.getenv('GW2_KEY')
    if not key:
        raise RuntimeError('GW2_KEY not set in environment')
    return {'Authorization': f'Bearer {key}'}


def gw2_get(path):
    url = f"{BASE}/{path}"
    resp = requests.get(url, headers=auth_header(), timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_orders():
    buys = gw2_get('commerce/transactions/current/buys')
    sells = gw2_get('commerce/transactions/current/sells')
    persist_current_orders(USER_ID, buys, sells)
    return buys, sells


def fetch_deliveries():
    return gw2_get('commerce/delivery')


def fetch_names(item_ids):
    names = {}
    ids = list(item_ids)
    for i in range(0, len(ids), 200):
        chunk = ids[i:i+200]
        data = gw2_get(f"items?ids={','.join(map(str, chunk))}")
        for entry in data:
            names[entry['id']] = entry['name']
    return names


def upsert_snapshot(grand_copper, item_ids):
    conn = sqlite3.connect('tp.sqlite')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS daily_snapshots (
        snapshot_date TEXT PRIMARY KEY, grand_copper INTEGER NOT NULL)''')
    today = date.today().isoformat()
    c.execute("""INSERT INTO daily_snapshots (snapshot_date, grand_copper)
        VALUES (?, ?) ON CONFLICT(snapshot_date) DO UPDATE
        SET grand_copper=excluded.grand_copper""", (today, grand_copper))
    if item_ids:
        ids_str = ','.join(map(str, item_ids))
        try:
            prices = gw2_get(f"commerce/prices?ids={ids_str}")
            c.execute('''CREATE TABLE IF NOT EXISTS daily_item_volume (
                item_id INTEGER, snapshot_date TEXT, volume INTEGER,
                PRIMARY KEY(item_id, snapshot_date))''')
            for entry in prices:
                c.execute("""INSERT INTO daily_item_volume
                    (item_id, snapshot_date, volume) VALUES (?, ?, ?)
                    ON CONFLICT(item_id, snapshot_date)
                    DO UPDATE SET volume=excluded.volume""",
                    (entry['id'], today, entry.get('volume', 0)))
        except Exception:
            pass  # volume tracking is non-critical
    conn.commit()
    conn.close()


@app.route('/')
def index():
    try:
        raw_buys, raw_sells = fetch_orders()
        delivery_data = fetch_deliveries()
    except Exception as e:
        return render_template('index.html', error=f"GW2 API unavailable: {e}",
                                buys=[], sells=[], deliveries=[],
                                total_buy_copper=0, total_sell_copper=0,
                                total_delivery_copper=0, grand_total_copper=0)

    coins = delivery_data.get('coins', 0)
    raw_deliveries_items = delivery_data.get('items', [])

    total_buy_copper = sum(o['price'] * o['quantity'] for o in raw_buys)
    total_sell_copper = sum(o['price'] * o['quantity'] for o in raw_sells)
    total_delivery_copper = coins + sum(
        d.get('unit_price', d.get('price', 0)) *
        d.get('count', d.get('quantity', 0))
        for d in raw_deliveries_items)
    grand_total_copper = total_buy_copper + total_sell_copper + total_delivery_copper

    ids = {o['item_id'] for o in raw_buys} | {o['item_id'] for o in raw_sells}
    delivery_ids = {d.get('item_id') or d.get('id') for d in raw_deliveries_items
                    if d.get('item_id') or d.get('id')}
    ids |= delivery_ids

    upsert_snapshot(grand_total_copper, ids)

    name_map = fetch_names(ids)

    buys = [{'name': name_map.get(o['item_id'], f"#{o['item_id']}"),
             'quantity': o['quantity'], 'price': o['price']} for o in raw_buys]
    sells = [{'name': name_map.get(o['item_id'], f"#{o['item_id']}"),
              'quantity': o['quantity'], 'price': o['price']} for o in raw_sells]
    deliveries = [{'name': name_map.get(d.get('item_id', d.get('id')),
                   f"#{d.get('item_id', d.get('id'))}"),
                   'quantity': d.get('count', d.get('quantity', 0)),
                   'price': d.get('unit_price', d.get('price', 0))}
                  for d in raw_deliveries_items]

    return render_template('index.html',
        buys=buys, sells=sells, deliveries=deliveries,
        total_buy_copper=total_buy_copper, total_sell_copper=total_sell_copper,
        total_delivery_copper=total_delivery_copper, grand_total_copper=grand_total_copper)


@app.route('/plan')
def plan():
    budget = float(request.args.get('budget', 0))
    horizon = int(request.args.get('horizon', 7))
    min_margin = float(request.args.get('min_margin', 5)) / 100
    min_fill_prob = float(request.args.get('min_fill_prob', 0)) / 100
    min_order = float(request.args.get('min_order', 0.01))

    if budget <= 0:
        try:
            wallet = gw2_get('account/wallet')
            raw_gold = sum(w['value'] for w in wallet) / 10000
            # Subtract gold already locked in buy orders
            orders_buys = gw2_get('commerce/transactions/current/buys')
            locked = sum(o['price'] * o['quantity'] for o in orders_buys) / 10000
            budget = round(max(0, raw_gold - locked), 1)
        except Exception:
            budget = 1000

    try:
        catalog = pd.read_csv('data/my_trading_items.csv')
        id_to_name = dict(zip(catalog['item_id'], catalog['item_name']))
    except FileNotFoundError:
        id_to_name = {}

    try:
        conn = sqlite3.connect('tp.sqlite')
        rows = conn.execute('''SELECT item_id, buy_price, sell_price, buy_qty, sell_qty
            FROM item_prices WHERE date = (SELECT MAX(date) FROM item_prices)''').fetchall()
        conn.close()

        if not rows:
            return render_template('plan.html', budget=budget, horizon=horizon,
                min_margin=int(min_margin*100), min_fill_prob=int(min_fill_prob*100),
                error='No price data yet. Run track_prices.py first.')

        prices = {}
        for r in rows:
            prices[str(r[0])] = {'buy_price': r[1], 'sell_price': r[2],
                                  'buy_qty': r[3], 'sell_qty': r[4]}
    except sqlite3.OperationalError:
        return render_template('plan.html', budget=budget, horizon=horizon,
            min_margin=int(min_margin*100), min_fill_prob=int(min_fill_prob*100),
            error='No price table yet. Run track_prices.py first.')

    models = {}
    try:
        models = load_models()
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    result = run_optimizer(models, prices, budget, horizon,
                            min_margin, min_fill_prob, min_order_gold=min_order)

    for row in result['summary']:
        row['item_name'] = id_to_name.get(row['item_id'], f"#{row['item_id']}")

    return render_template('plan.html', result=result,
        budget=int(budget), horizon=horizon,
        min_margin=int(min_margin*100), min_fill_prob=int(min_fill_prob*100))


@app.route('/favorites')
def favorites():
    try:
        catalog = pd.read_csv('data/my_trading_items.csv')
    except FileNotFoundError:
        return render_template('favorites.html', items=[], error='No item catalog found.')

    # Fetch live prices from GW2 API (batched, max 200 per call)
    live_prices = {}
    item_ids = catalog['item_id'].tolist()
    for i in range(0, len(item_ids), 200):
        chunk = item_ids[i:i+200]
        try:
            data = gw2_get(f"commerce/prices?ids={','.join(map(str, chunk))}")
            for entry in data:
                live_prices[entry['id']] = {
                    'buy_price':  entry['buys']['unit_price'],
                    'sell_price': entry['sells']['unit_price'],
                }
        except Exception:
            continue  # partial failure: skip this chunk, keep going

    # Load starred items
    conn = sqlite3.connect('tp.sqlite')
    starred = set(r[0] for r in conn.execute(
        "SELECT item_id FROM favorites WHERE user_id=?", (USER_ID,)))
    conn.close()

    # Build item list
    items = []
    for _, row in catalog.iterrows():
        item_id = int(row['item_id'])
        p = live_prices.get(item_id, {})
        buy_price = p.get('buy_price', 0)
        sell_price = p.get('sell_price', 0)
        margin = (sell_price - buy_price) / buy_price if buy_price > 0 else 0

        items.append({
            'item_id': item_id,
            'name': row['item_name'],
            'buy_price': buy_price,
            'sell_price': sell_price,
            'margin': margin,
            'starred': item_id in starred,
        })

    items.sort(key=lambda x: (not x['starred'], -x['margin']))
    return render_template('favorites.html', items=items)


@app.post('/favorites/toggle/<int:item_id>')
def toggle_favorite(item_id):
    from favorites import add_fav, remove_fav, list_favs
    starred = list_favs(USER_ID)
    if item_id in starred:
        remove_fav(USER_ID, item_id)
    else:
        add_fav(USER_ID, item_id)
    return redirect(url_for('favorites'))


@app.post('/login')
def login():
    uid = verify_user(request.form.get('email',''), request.form.get('password',''))
    if uid: session['user_id'] = uid
    return redirect(url_for('index'))


@app.post('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.get('/register')
def register_form():
    return render_template('register.html')


@app.post('/register')
def register_submit():
    email = request.form.get('email','').strip()
    pw = request.form.get('password','')
    key = request.form.get('api_key','').strip()
    if email and pw and key:
        session['user_id'] = create_user(email, pw, key)
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True)
