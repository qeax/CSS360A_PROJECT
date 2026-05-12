from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, func, text

from app.db import Base


class Car(Base):
    __tablename__ = "cars"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    brand = Column(String(100), nullable=False, index=True)
    model = Column(String(100), nullable=False, index=True)
    year = Column(Integer, nullable=False, index=True)
    price = Column(Float, nullable=False, index=True)
    repair_cost = Column(Float, nullable=False, default=0)
    resale_value = Column(Float, nullable=False)
    mileage = Column(Integer, nullable=True)
    condition = Column(String(50), nullable=True)

    image_url = Column(String(512), nullable=True)
    source = Column(String(50), nullable=False, server_default=text("'manual'"))
    external_listing_id = Column(String(128), nullable=True, index=True)
    listing_url = Column(String(1024), nullable=True)
    raw_listing_json = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
