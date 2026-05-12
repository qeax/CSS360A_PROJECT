from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.db import Base


class UserAuditEvent(Base):
    __tablename__ = "user_audit_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action = Column(String(128), nullable=False)
    resource_type = Column(String(64), nullable=True)
    resource_id = Column(String(128), nullable=True)
    payload = Column("metadata", JSON, nullable=True)
    ip_address_hash = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="audit_events")
