from sqlalchemy import Column, DateTime, Integer, String, Text, func, text
from sqlalchemy.orm import relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(320), nullable=False, unique=True, index=True)
    azure_oid = Column(String(255), nullable=False, unique=True, index=True)

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

    audit_events = relationship(
        "UserAuditEvent",
        back_populates="user",
        passive_deletes=True,
    )
