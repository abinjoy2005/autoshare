from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('rider', 'driver', 'admin')", name="ck_users_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="rider")
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="driver")
    rides_as_rider: Mapped[list["Ride"]] = relationship(
        back_populates="rider", foreign_keys="Ride.rider_id"
    )
    rides_as_driver: Mapped[list["Ride"]] = relationship(
        back_populates="driver", foreign_keys="Ride.driver_id"
    )
    location: Mapped["Location | None"] = relationship(back_populates="driver")


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        CheckConstraint("capacity BETWEEN 1 AND 8", name="ck_vehicles_capacity"),
        CheckConstraint(
            "verification_status IN ('pending', 'verified', 'rejected')",
            name="ck_vehicles_verification_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    driver_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    license_plate: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    make_model: Mapped[str] = mapped_column(String(120), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    driver: Mapped[User] = relationship(back_populates="vehicles")


class Ride(Base):
    __tablename__ = "rides"
    __table_args__ = (
        CheckConstraint(
            "status IN ('requested', 'accepted', 'in_transit', 'completed')",
            name="ck_rides_status",
        ),
        CheckConstraint("passenger_count BETWEEN 1 AND 8", name="ck_rides_passengers"),
        CheckConstraint("fare_amount >= 0", name="ck_rides_fare"),
        CheckConstraint(
            "(pickup_latitude IS NULL) = (pickup_longitude IS NULL)",
            name="ck_rides_pickup_coordinates",
        ),
        CheckConstraint(
            "(dropoff_latitude IS NULL) = (dropoff_longitude IS NULL)",
            name="ck_rides_dropoff_coordinates",
        ),
        Index("ix_rides_dispatch", "status", "created_at"),
        Index(
            "uq_one_active_ride_per_driver",
            "driver_id",
            unique=True,
            postgresql_where=text(
                "driver_id IS NOT NULL AND status IN ('accepted', 'in_transit')"
            ),
            sqlite_where=text(
                "driver_id IS NOT NULL AND status IN ('accepted', 'in_transit')"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    rider_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    driver_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    pickup: Mapped[str] = mapped_column(String(255), nullable=False)
    dropoff: Mapped[str] = mapped_column(String(255), nullable=False)
    pickup_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    pickup_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    dropoff_latitude: Mapped[float | None] = mapped_column(Float)
    dropoff_longitude: Mapped[float | None] = mapped_column(Float)
    passenger_count: Mapped[int] = mapped_column(Integer, nullable=False)
    fare_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="requested")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    rider: Mapped[User] = relationship(
        back_populates="rides_as_rider", foreign_keys=[rider_id]
    )
    driver: Mapped[User | None] = relationship(
        back_populates="rides_as_driver", foreign_keys=[driver_id]
    )
    declines: Mapped[list["RideDecline"]] = relationship(back_populates="ride")


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_locations_latitude"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_locations_longitude"),
        Index("ix_locations_updated_at", "updated_at"),
        Index("ix_locations_coordinates", "latitude", "longitude"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    driver_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    driver: Mapped[User] = relationship(back_populates="location")


class RideDecline(Base):
    __tablename__ = "ride_declines"
    __table_args__ = (UniqueConstraint("ride_id", "driver_id", name="uq_ride_decline"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ride_id: Mapped[int] = mapped_column(
        ForeignKey("rides.id", ondelete="CASCADE"), nullable=False
    )
    driver_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    ride: Mapped[Ride] = relationship(back_populates="declines")
