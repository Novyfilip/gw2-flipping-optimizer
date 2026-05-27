"""from sqlalchemy import Integer, String, Text, CheckConstraint, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from .engine import Base
from datetime import datetime

class OpenOrder(Base):
    __tablename__ = "open_orders"
    order_id:       Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id:        Mapped[int] = mapped_column(Integer, nullable=False)
    side:           Mapped[str] = mapped_column(String, nullable=False)  # 'buy'|'sell'
    unit_price:     Mapped[int] = mapped_column(Integer, nullable=False)  # copper
    quantity_total: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_open:  Mapped[int] = mapped_column(Integer, nullable=False)
    listing_fee:    Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at:     Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at:     Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_poll: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    __table_args__ = (CheckConstraint("side in ('buy','sell')"),)

class Fill(Base):
    __tablename__ = "fills"
    fill_id:    Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id:   Mapped[int | None] = mapped_column(Integer)
    item_id:    Mapped[int] = mapped_column(Integer, nullable=False)
    side:       Mapped[str] = mapped_column(String, nullable=False)
    quantity:   Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at:Mapped[datetime] = mapped_column(DateTime, nullable=False)
    exchange_fee: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    __table_args__ = (CheckConstraint("side in ('buy','sell')"),)

class DailySnapshot(Base):
    __tablename__ = "daily_snapshots"
    snapshot_date: Mapped[str] = mapped_column(String, primary_key=True)  # YYYY-MM-DD
    grand_copper:  Mapped[int] = mapped_column(Integer, nullable=False)

class DailyItemVolume(Base):
    __tablename__ = "daily_item_volume"
    item_id:       Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_date: Mapped[str] = mapped_column(String, primary_key=True)
    volume:        Mapped[int] = mapped_column(Integer, nullable=False)
"""