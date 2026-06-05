from sqlalchemy import Column, DateTime, Float, Integer, String, func

from app.db import Base


class VehiclePriceSegment(Base):
    __tablename__ = "vehicle_price_segments"

    segment_key = Column(String(160), primary_key=True)
    brand = Column(String(100), nullable=False, index=True)
    model = Column(String(100), nullable=False, index=True)
    year_bucket = Column(Integer, nullable=False, index=True)
    sample_count = Column(Integer, nullable=False, default=0)
    median_price = Column(Float, nullable=False)
    p25_price = Column(Float, nullable=True)
    p75_price = Column(Float, nullable=True)
    median_mileage = Column(Integer, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
