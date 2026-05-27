# db.py — minimal multi-user persistence (SQLite)

import sqlite3
from datetime import datetime

DB_PATH = "tp.sqlite"

def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    # SQLite foreign keys are OFF by default; leave off so we don't block inserts
    return c

def ensure_tables():
    with _conn() as conn:
        cur = conn.cursor()

        # Simple users table (not used yet by app routes; no password/login logic here)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
          user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
          email         TEXT UNIQUE,
          password_hash TEXT,
          salt          TEXT,
          api_key       TEXT,
          created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")

        # Live open orders per user
        cur.execute("""
        CREATE TABLE IF NOT EXISTS open_orders (
          user_id        INTEGER NOT NULL,
          order_id       INTEGER NOT NULL,
          item_id        INTEGER NOT NULL,
          side           TEXT NOT NULL CHECK(side IN ('buy','sell')),
          unit_price     INTEGER NOT NULL,
          quantity_total INTEGER NOT NULL,
          quantity_open  INTEGER NOT NULL,
          listing_fee    INTEGER NOT NULL DEFAULT 0,   -- 5% for sells at placement
          created_at     TEXT NOT NULL,
          updated_at     TEXT NOT NULL,
          last_seen_poll TEXT NOT NULL,
          PRIMARY KEY (user_id, order_id)
        )""")

        # Fills derived from quantity deltas (and later cross-checked with history)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS fills (
          fill_id      INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id      INTEGER NOT NULL,
          order_id     INTEGER,
          item_id      INTEGER NOT NULL,
          side         TEXT NOT NULL CHECK(side IN ('buy','sell')),
          quantity     INTEGER NOT NULL,
          unit_price   INTEGER NOT NULL,
          occurred_at  TEXT NOT NULL,
          exchange_fee INTEGER NOT NULL DEFAULT 0       -- 10% on sells per filled qty
        )""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            user_id    INTEGER NOT NULL,
            item_id    INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, item_id)
        );""")

        conn.commit()

def persist_current_orders(user_id: int, buys: list[dict], sells: list[dict]) -> None:
    """
    Idempotent diff for one user:
    - New sell orders record 5% listing fee on full qty (non-refundable).
    - If quantity_open drops, insert a fill for the delta (10% exchange fee on sells).
    - Orders that vanish are removed from open_orders (treated as closed between polls).
    """
    ensure_tables()
    now = datetime.utcnow().isoformat(timespec="seconds")
    all_orders = [{**o, "side": "buy"} for o in buys] + [{**o, "side": "sell"} for o in sells]

    with _conn() as conn:
        cur = conn.cursor()

        # previous state for this user
        prev = {
            r["order_id"]: dict(r)
            for r in cur.execute(
                "SELECT order_id, item_id, side, unit_price, quantity_total, quantity_open "
                "FROM open_orders WHERE user_id=?",
                (user_id,),
            )
        }

        seen = set()

        for o in all_orders:
            oid = o["id"]; item = o["item_id"]; side = o["side"]
            price = o["price"]; qty = o["quantity"]
            created = o.get("created") or now

            if oid in prev:
                old_open = prev[oid]["quantity_open"]
                new_open = qty
                delta = max(0, old_open - new_open)
                if delta > 0:
                    exh_fee = (price * delta * 10) // 100 if side == "sell" else 0
                    cur.execute(
                        """INSERT INTO fills(user_id,order_id,item_id,side,quantity,unit_price,occurred_at,exchange_fee)
                           VALUES(?,?,?,?,?,?,?,?)""",
                        (user_id, oid, item, side, delta, price, now, exh_fee),
                    )

                # upsert open order
                cur.execute("""
                  INSERT INTO open_orders(user_id,order_id,item_id,side,unit_price,quantity_total,quantity_open,listing_fee,created_at,updated_at,last_seen_poll)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?)
                  ON CONFLICT(user_id,order_id) DO UPDATE SET
                    item_id=excluded.item_id,
                    side=excluded.side,
                    unit_price=excluded.unit_price,
                    quantity_total=excluded.quantity_total,
                    quantity_open=excluded.quantity_open,
                    updated_at=excluded.updated_at,
                    last_seen_poll=excluded.last_seen_poll
                """, (user_id, oid, item, side, price, qty, qty, 0, created, now, now))

            else:
                # new order: pay 5% listing fee on full qty for sells
                listing = (price * qty * 5) // 100 if side == "sell" else 0
                cur.execute("""
                  INSERT INTO open_orders(user_id,order_id,item_id,side,unit_price,quantity_total,quantity_open,listing_fee,created_at,updated_at,last_seen_poll)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """, (user_id, oid, item, side, price, qty, qty, listing, created, now, now))

            seen.add(oid)

        # remove vanished open orders for this user
        if seen:
            q = f"SELECT order_id FROM open_orders WHERE user_id=? AND order_id NOT IN ({','.join('?' for _ in seen)})"
            missing = cur.execute(q, (user_id, *seen)).fetchall()
        else:
            missing = cur.execute("SELECT order_id FROM open_orders WHERE user_id=?", (user_id,)).fetchall()

        for r in missing:
            cur.execute("DELETE FROM open_orders WHERE user_id=? AND order_id=?", (user_id, r["order_id"]))

        conn.commit()
        
