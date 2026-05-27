# db.py — SQLite persistence for GW2 Trading Post Optimizer

import sqlite3

DB_PATH = "tp.sqlite"

def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def ensure_tables():
    with _conn() as conn:
        cur = conn.cursor()

        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT UNIQUE,
            password_hash TEXT,
            salt          TEXT,
            api_key       TEXT,
            created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")

        cur.execute("""CREATE TABLE IF NOT EXISTS open_orders (
            user_id        INTEGER NOT NULL,
            order_id       INTEGER NOT NULL,
            item_id        INTEGER NOT NULL,
            side           TEXT NOT NULL CHECK(side IN ('buy','sell')),
            unit_price     INTEGER NOT NULL,
            quantity_total INTEGER NOT NULL,
            quantity_open  INTEGER NOT NULL,
            listing_fee    INTEGER NOT NULL DEFAULT 0,
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL,
            last_seen_poll TEXT NOT NULL,
            PRIMARY KEY (user_id, order_id)
        )""")

        cur.execute("""CREATE TABLE IF NOT EXISTS fills (
            fill_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            order_id     INTEGER,
            item_id      INTEGER NOT NULL,
            side         TEXT NOT NULL CHECK(side IN ('buy','sell')),
            quantity     INTEGER NOT NULL,
            unit_price   INTEGER NOT NULL,
            occurred_at  TEXT NOT NULL,
            exchange_fee INTEGER NOT NULL DEFAULT 0
        )""")

        conn.commit()
