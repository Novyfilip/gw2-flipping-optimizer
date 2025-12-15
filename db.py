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

        conn.commit()


