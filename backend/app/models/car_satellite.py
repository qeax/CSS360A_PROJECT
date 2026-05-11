from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class CarLocation(Base):
    __tablename__ = "car_locations"

    car_id = Column(Integer, ForeignKey("cars.id", ondelete="CASCADE"), primary_key=True)
    country = Column(String(128), nullable=True)
    region = Column(String(128), nullable=True)
    city = Column(String(256), nullable=True)
    postal_code_masked = Column(String(32), nullable=True)
    latitude = Column(Numeric(10, 7), nullable=True)
    longitude = Column(Numeric(10, 7), nullable=True)

    car = relationship("Car", back_populates="location")


class CarListingTerms(Base):
    __tablename__ = "car_listing_terms"

    car_id = Column(Integer, ForeignKey("cars.id", ondelete="CASCADE"), primary_key=True)
    ship_to_home = Column(Boolean, nullable=False, default=False)
    local_pickup = Column(Boolean, nullable=False, default=False)
    in_store_pickup = Column(Boolean, nullable=False, default=False)
    delivery_options_raw = Column(JSON, nullable=True)

    car = relationship("Car", back_populates="listing_terms")


class CarMedia(Base):
    __tablename__ = "car_media"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    car_id = Column(Integer, ForeignKey("cars.id", ondelete="CASCADE"), nullable=False, index=True)
    sort_order = Column(Integer, nullable=False, default=0)
    url = Column(String(2048), nullable=False)

    car = relationship("Car", back_populates="media")


class VehicleAspectSnapshot(Base):
    __tablename__ = "vehicle_aspect_snapshots"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    car_id = Column(Integer, ForeignKey("cars.id", ondelete="CASCADE"), nullable=False, index=True)
    captured_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    aspects_json = Column(JSON, nullable=True)

    car = relationship("Car", back_populates="aspect_snapshots")


class VehicleHistoryReport(Base):
    __tablename__ = "vehicle_history_reports"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    car_id = Column(Integer, ForeignKey("cars.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(64), nullable=False)
    external_report_id = Column(String(256), nullable=True)
    payload_json = Column(JSON, nullable=True)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    car = relationship("Car", back_populates="history_reports")
