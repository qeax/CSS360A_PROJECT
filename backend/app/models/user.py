from sqlalchemy import Column, DateTime, Integer, String, Text, func, text
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(320), nullable=False, unique=True, index=True)
    azure_oid = Column(String(255), nullable=False, unique=True, index=True)
    display_name = Column(String(255), nullable=True)
    profile_picture_url = Column(Text().with_variant(MEDIUMTEXT, "mysql"), nullable=True)

    account_status = Column(String(32), nullable=False, server_default=text("'active'"))
    restricted_until = Column(DateTime(timezone=True), nullable=True)
    moderation_note = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    watch_last_full_check_at = Column(DateTime(timezone=True), nullable=True)

    audit_events = relationship(
        "UserAuditEvent",
        back_populates="user",
        passive_deletes=True,
    )
    watchlist_items = relationship(
        "UserWatchlistItem",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    notifications = relationship(
        "UserNotification",
        back_populates="user",
        cascade="all, delete-orphan",
    )
