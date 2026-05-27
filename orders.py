# orders.py — Order persistence and fill detection via quantity delta

from db import _conn, ensure_tables
from datetime import datetime


def persist_current_orders(user_id: int, buys: list[dict], sells: list[dict]) -> None:
    """Idempotent diff for one user. Detects fills when quantity_open drops.

    - New sell orders record 5% listing fee on full quantity.
    - If quantity_open drops, insert a fill for the delta (10% exchange fee on sells).
    - Orders that vanish between polls are removed from open_orders.
    """
    ensure_tables()
    now = datetime.utcnow().isoformat(timespec="seconds")
    all_orders = [{**o, "side": "buy"} for o in buys] + [{**o, "side": "sell"} for o in sells]

    with _conn() as conn:
        cur = conn.cursor()

        prev = {
            r["order_id"]: dict(r)
            for r in cur.execute(
                "SELECT order_id, item_id, side, unit_price, quantity_total, quantity_open "
                "FROM open_orders WHERE user_id=?", (user_id,)
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
                        "INSERT INTO fills(user_id,order_id,item_id,side,quantity,unit_price,occurred_at,exchange_fee) "
                        "VALUES(?,?,?,?,?,?,?,?)",
                        (user_id, oid, item, side, delta, price, now, exh_fee),
                    )

                cur.execute("""INSERT INTO open_orders(user_id,order_id,item_id,side,unit_price,
                    quantity_total,quantity_open,listing_fee,created_at,updated_at,last_seen_poll)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(user_id,order_id) DO UPDATE SET
                    item_id=excluded.item_id, side=excluded.side,
                    unit_price=excluded.unit_price, quantity_total=excluded.quantity_total,
                    quantity_open=excluded.quantity_open, updated_at=excluded.updated_at,
                    last_seen_poll=excluded.last_seen_poll""",
                    (user_id, oid, item, side, price, qty, qty, 0, created, now, now))

            else:
                listing = (price * qty * 5) // 100 if side == "sell" else 0
                cur.execute("""INSERT INTO open_orders(user_id,order_id,item_id,side,unit_price,
                    quantity_total,quantity_open,listing_fee,created_at,updated_at,last_seen_poll)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (user_id, oid, item, side, price, qty, qty, listing, created, now, now))

            seen.add(oid)

        if seen:
            q = f"SELECT order_id FROM open_orders WHERE user_id=? AND order_id NOT IN ({','.join('?' for _ in seen)})"
            missing = cur.execute(q, (user_id, *seen)).fetchall()
        else:
            missing = cur.execute("SELECT order_id FROM open_orders WHERE user_id=?", (user_id,)).fetchall()

        for r in missing:
            cur.execute("DELETE FROM open_orders WHERE user_id=? AND order_id=?", (user_id, r["order_id"]))

        conn.commit()
