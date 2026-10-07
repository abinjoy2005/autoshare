from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    ride_requests: Mapped[list["RideRequest"]] = relationship(back_populates="user")


class ActiveRideGroup(Base):
    __tablename__ = "active_ride_groups"
    __table_args__ = (
        CheckConstraint("current_passengers >= 2 AND current_passengers <= max_passengers"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    origin: Mapped[str] = mapped_column(String(255), nullable=False)
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    current_passengers: Mapped[int] = mapped_column(Integer, nullable=False)
    max_passengers: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    departure_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    ride_requests: Mapped[list["RideRequest"]] = relationship(back_populates="group")


class RideRequest(Base):
    __tablename__ = "ride_requests"
    __table_args__ = (CheckConstraint("passenger_count >= 1 AND passenger_count <= 3"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    group_id: Mapped[int | None] = mapped_column(ForeignKey("active_ride_groups.id"))
    origin: Mapped[str] = mapped_column(String(255), nullable=False)
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    passenger_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    departure_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped[User | None] = relationship(back_populates="ride_requests")
    group: Mapped[ActiveRideGroup | None] = relationship(back_populates="ride_requests")
