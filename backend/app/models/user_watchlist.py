"""User watchlist (tracked listings, max 10 per user)."""

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.db import Base


class UserWatchlistItem(Base):
    __tablename__ = "user_watchlist_items"
    __table_args__ = (UniqueConstraint("user_id", "car_id", name="uq_user_watchlist_user_car"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    car_id = Column(
        Integer,
        ForeignKey("cars.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    last_snapshot_json = Column(JSON, nullable=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="watchlist_items")
    car = relationship("Car", back_populates="watchlist_items")
