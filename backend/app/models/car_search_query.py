from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.db import Base


class CarSearchQuery(Base):
    __tablename__ = "car_search_queries"
    __table_args__ = (
        UniqueConstraint("car_id", "query_key", name="uq_car_search_queries_car_query_key"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    car_id = Column(Integer, ForeignKey("cars.id", ondelete="CASCADE"), nullable=False, index=True)
    query_text = Column(String(256), nullable=False)
    query_key = Column(String(128), nullable=False, index=True)
    source = Column(String(32), nullable=False, server_default="ebay")
    hit_count = Column(Integer, nullable=False, server_default="1")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    car = relationship("Car", back_populates="search_queries")
