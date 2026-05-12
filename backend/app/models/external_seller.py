from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db import Base


class ExternalSeller(Base):
    __tablename__ = "external_sellers"
    __table_args__ = (
        UniqueConstraint(
            "platform",
            "external_seller_id",
            name="uq_external_sellers_platform_external_id",
        ),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    platform = Column(String(32), nullable=False, default="ebay")
    external_seller_id = Column(String(128), nullable=False)
    username = Column(String(255), nullable=True)
    profile_url = Column(String(1024), nullable=True)
    synced_at = Column(DateTime(timezone=True), nullable=True)

    cars = relationship("Car", back_populates="external_seller")
