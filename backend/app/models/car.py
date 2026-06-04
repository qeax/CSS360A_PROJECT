from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import relationship

from app.db import Base


class Car(Base):
    __tablename__ = "cars"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "external_listing_id",
            name="uq_cars_source_external_listing_id",
        ),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    brand = Column(String(100), nullable=False, index=True)
    model = Column(String(100), nullable=False, index=True)
    year = Column(Integer, nullable=True, index=True)
    price = Column(Float, nullable=False, index=True)
    price_known = Column(Boolean, nullable=False, server_default=text("1"))
    repair_cost = Column(Float, nullable=False, default=0)
    resale_value = Column(Float, nullable=False)
    mileage = Column(Integer, nullable=True)
    condition = Column(String(50), nullable=True)
    vehicle_title = Column(String(128), nullable=True)

    image_url = Column(String(512), nullable=True)
    source = Column(String(50), nullable=False, server_default=text("'manual'"))
    external_listing_id = Column(String(128), nullable=True, index=True)
    listing_url = Column(String(1024), nullable=True)
    raw_listing_json = Column(JSON, nullable=True)

    seller_id = Column(
        Integer,
        ForeignKey("external_sellers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    listing_ends_at = Column(DateTime(timezone=True), nullable=True)
    auction_ended_at = Column(DateTime(timezone=True), nullable=True)
    ingest_search_key = Column(String(128), nullable=True, index=True)
    bid_count = Column(Integer, nullable=True)
    listing_format = Column(String(50), nullable=True)
    description_summary = Column(String(1024), nullable=True)
    description_full = Column(Text, nullable=True)
    api_synced_at = Column(DateTime(timezone=True), nullable=True)
    seller_item_revision = Column(String(64), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    external_seller = relationship("ExternalSeller", back_populates="cars")
    location = relationship(
        "CarLocation",
        back_populates="car",
        uselist=False,
        cascade="all, delete-orphan",
    )
    listing_terms = relationship(
        "CarListingTerms",
        back_populates="car",
        uselist=False,
        cascade="all, delete-orphan",
    )
    media = relationship(
        "CarMedia",
        back_populates="car",
        cascade="all, delete-orphan",
        order_by="CarMedia.sort_order",
    )
    aspect_snapshots = relationship(
        "VehicleAspectSnapshot",
        back_populates="car",
        cascade="all, delete-orphan",
    )
    history_reports = relationship(
        "VehicleHistoryReport",
        back_populates="car",
        cascade="all, delete-orphan",
    )
    watchlist_items = relationship(
        "UserWatchlistItem",
        back_populates="car",
        cascade="all, delete-orphan",
    )
