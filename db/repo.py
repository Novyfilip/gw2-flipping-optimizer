"""from datetime import datetime
from sqlalchemy import select, update, insert, func
from .engine import SessionLocal, Base, engine
from .models import OpenOrder, Fill, DailySnapshot, DailyItemVolume

def init_db():
    Base.metadata.create_all(engine)

def persist_current_orders(buys: list[dict], sells: list[dict]) -> None:
    now = datetime.utcnow()
    all_orders = [{**o,'side':'buy'} for o in buys] + [{**o,'side':'sell'} for o in sells]
    seen = set()
    with SessionLocal() as s:
        # cache previous open qty
        prev = {oo.order_id: oo for oo in s.scalars(select(OpenOrder))}
        for o in all_orders:
            oid, item, side = o["id"], o["item_id"], o["side"]
            price, qty = o["price"], o["quantity"]
            created = datetime.fromisoformat(o.get("created")) if o.get("created") else now
            seen.add(oid)

            if oid in prev:
                oo = prev[oid]
                delta = max(0, oo.quantity_open - qty)
                if delta > 0:
                    exh_fee = (price * delta * 10) // 100 if side == "sell" else 0
                    s.add(Fill(order_id=oid, item_id=item, side=side, quantity=delta,
                               unit_price=price, occurred_at=now, exchange_fee=exh_fee))
                # upsert
                s.execute(update(OpenOrder).where(OpenOrder.order_id==oid).values(
                    item_id=item, side=side, unit_price=price, quantity_total=qty,
                    quantity_open=qty, updated_at=now, last_seen_poll=now
                ))
            else:
                listing = (price * qty * 5) // 100 if side == "sell" else 0
                s.add(OpenOrder(order_id=oid, item_id=item, side=side,
                                unit_price=price, quantity_total=qty, quantity_open=qty,
                                listing_fee=listing, created_at=created,
                                updated_at=now, last_seen_poll=now))
        # delete vanished (closed) orders
        if seen:
            s.query(OpenOrder).filter(~OpenOrder.order_id.in_(seen)).delete(synchronize_session=False)
        else:
            s.query(OpenOrder).delete()
        s.commit()

def upsert_snapshot(grand_copper: int, item_ids: set[int], fetch_prices_fn) -> None:
    # fetch_prices_fn(ids_chunk) -> list of dicts with {'id','volume'}
    today = datetime.utcnow().date().isoformat()
    with SessionLocal() as s:
        # daily_snapshots
        row = s.get(DailySnapshot, today)
        if row: row.grand_copper = grand_copper
        else:   s.add(DailySnapshot(snapshot_date=today, grand_copper=grand_copper))

        ids = list(item_ids)
        for i in range(0, len(ids), 200):
            chunk = ids[i:i+200]
            prices = fetch_prices_fn(chunk)
            for entry in prices:
                key = {"item_id": entry["id"], "snapshot_date": today}
                existing = s.get(DailyItemVolume, (key["item_id"], key["snapshot_date"]))
                if existing: existing.volume = entry.get("volume", 0)
                else:        s.add(DailyItemVolume(volume=entry.get("volume", 0), **key))
        s.commit()"""
