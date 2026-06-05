"""Pending eBay search summaries between enrich waves (not yet in cars table)."""

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func

from app.db import Base


class EbaySyncBatch(Base):
    __tablename__ = "ebay_sync_batches"
    __table_args__ = (
        UniqueConstraint("user_id", "search_key", name="uq_ebay_sync_batches_user_search_key"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    search_key = Column(String(128), nullable=False, index=True)
    search_query = Column(String(512), nullable=False)
    summaries_json = Column(JSON, nullable=False)
    cursor = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
