import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Location, Ride, RideDecline, User, Vehicle
from app.routers.drivers import _distance_km, _has_verified_vehicle
from app.schemas import (
    DriverLocationPublic,
    RideCreate,
    RideDecision,
    RidePublic,
    RideStatusUpdate,
)
from app.security import get_current_user, require_role

router = APIRouter(prefix="/api", tags=["rides and dispatch"])
rider_only = require_role("rider")
driver_only = require_role("driver")


def _dispatch_radius_km() -> float:
    try:
        radius = float(os.getenv("DISPATCH_RADIUS_KM", "25"))
    except ValueError as exc:
        raise HTTPException(
            status_code=503, detail="DISPATCH_RADIUS_KM must be a valid number"
        ) from exc
    if radius <= 0 or radius > 100:
        raise HTTPException(
            status_code=503, detail="DISPATCH_RADIUS_KM must be between 0 and 100"
        )
    return radius


def _fare_estimate(payload: RideCreate) -> float:
    try:
        base_fare = float(os.getenv("RIDE_BASE_FARE", "50"))
        per_km = float(os.getenv("RIDE_RATE_PER_KM", "15"))
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Ride fare settings must be numeric") from exc
    if base_fare < 0 or per_km < 0:
        raise HTTPException(status_code=503, detail="Ride fare settings cannot be negative")
    if payload.dropoff_latitude is None:
        return round(base_fare, 2)
    distance = _distance_km(
        payload.pickup_latitude,
        payload.pickup_longitude,
        payload.dropoff_latitude,
        payload.dropoff_longitude,
    )
    return round(base_fare + distance * per_km, 2)


def _public_ride(ride: Ride) -> RidePublic:
    return RidePublic.model_validate(ride)


@router.post("/rides", response_model=RidePublic, status_code=201)
def request_ride(
    payload: RideCreate,
    db: Session = Depends(get_db),
    rider: User = Depends(rider_only),
) -> RidePublic:
    ride = Ride(
        rider_id=rider.id,
        pickup=payload.pickup.strip(),
        dropoff=payload.dropoff.strip(),
        pickup_latitude=payload.pickup_latitude,
        pickup_longitude=payload.pickup_longitude,
        dropoff_latitude=payload.dropoff_latitude,
        dropoff_longitude=payload.dropoff_longitude,
        passenger_count=payload.passenger_count,
        fare_amount=_fare_estimate(payload),
        status="requested",
    )
    db.add(ride)
    db.commit()
    db.refresh(ride)
    return _public_ride(ride)


@router.get("/rides/mine", response_model=list[RidePublic])
def my_rides(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[RidePublic]:
    column = Ride.rider_id if user.role == "rider" else Ride.driver_id
    rides = db.scalars(
        select(Ride).where(column == user.id).order_by(Ride.created_at.desc()).limit(100)
    )
    return [_public_ride(ride) for ride in rides]


@router.get(
    "/rides/{ride_id}/driver-location", response_model=DriverLocationPublic
)
def ride_driver_location(
    ride_id: int,
    db: Session = Depends(get_db),
    rider: User = Depends(rider_only),
) -> DriverLocationPublic:
    ride = db.get(Ride, ride_id)
    if ride is None or ride.rider_id != rider.id:
        raise HTTPException(status_code=404, detail="Ride not found")
    if ride.status not in {"accepted", "in_transit"} or ride.driver_id is None:
        raise HTTPException(status_code=409, detail="Ride has no active driver")
    location = db.scalar(select(Location).where(Location.driver_id == ride.driver_id))
    if location is None:
        raise HTTPException(status_code=404, detail="Driver location is not available")
    updated_at = location.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    if updated_at < datetime.now(timezone.utc) - timedelta(minutes=2):
        raise HTTPException(status_code=404, detail="Driver location is stale")
    return DriverLocationPublic(
        latitude=location.latitude,
        longitude=location.longitude,
        updated_at=updated_at,
    )


@router.get("/driver/rides/requests", response_model=list[RidePublic])
def pending_driver_requests(
    db: Session = Depends(get_db),
    driver: User = Depends(driver_only),
) -> list[RidePublic]:
    if not driver.is_online or not driver.is_verified or not _has_verified_vehicle(db, driver.id):
        return []
    location = db.scalar(select(Location).where(Location.driver_id == driver.id))
    if location is None:
        return []
    if db.scalar(
        select(Ride.id).where(
            Ride.driver_id == driver.id,
            Ride.status.in_(("accepted", "in_transit")),
        )
    ) is not None:
        return []
    radius_km = _dispatch_radius_km()
    declines = select(RideDecline.id).where(
        RideDecline.ride_id == Ride.id, RideDecline.driver_id == driver.id
    )
    rows = db.scalars(
        select(Ride)
        .join(Vehicle, Vehicle.driver_id == driver.id)
        .where(
            Ride.status == "requested",
            Vehicle.is_active.is_(True),
            Vehicle.verification_status == "verified",
            Vehicle.capacity >= Ride.passenger_count,
            ~declines.exists(),
        )
        .distinct()
        .order_by(Ride.created_at)
        .limit(100)
    )
    results = []
    for ride in rows:
        if (
            _distance_km(
                location.latitude,
                location.longitude,
                ride.pickup_latitude,
                ride.pickup_longitude,
            )
            <= radius_km
        ):
            results.append(ride)
    return [_public_ride(ride) for ride in results]


@router.post("/driver/rides/{ride_id}/decision", response_model=RidePublic)
def decide_ride(
    ride_id: int,
    decision: RideDecision,
    db: Session = Depends(get_db),
    driver: User = Depends(driver_only),
) -> RidePublic:
    ride = db.scalar(select(Ride).where(Ride.id == ride_id).with_for_update())
    if ride is None:
        raise HTTPException(status_code=404, detail="Ride not found")
    if ride.status != "requested":
        raise HTTPException(status_code=409, detail="Ride is no longer available")

    if not driver.is_online or not driver.is_verified or not _has_verified_vehicle(db, driver.id):
        raise HTTPException(status_code=403, detail="Verified online driver status is required")

    active_ride = db.scalar(
        select(Ride.id).where(
            Ride.driver_id == driver.id,
            Ride.status.in_(("accepted", "in_transit")),
        )
    )
    if active_ride is not None:
        raise HTTPException(status_code=409, detail="Driver already has an active ride")

    capacities = db.scalars(
        select(Vehicle.capacity).where(
            Vehicle.driver_id == driver.id,
            Vehicle.is_active.is_(True),
            Vehicle.verification_status == "verified",
        )
    ).all()
    if not capacities or max(capacities) < ride.passenger_count:
        raise HTTPException(status_code=403, detail="No verified vehicle can serve this ride")
    location = db.scalar(select(Location).where(Location.driver_id == driver.id))
    now = datetime.now(timezone.utc)
    if location is None:
        raise HTTPException(status_code=409, detail="Update your live location before responding")
    location_updated_at = location.updated_at
    if location_updated_at.tzinfo is None:
        location_updated_at = location_updated_at.replace(tzinfo=timezone.utc)
    else:
        location_updated_at = location_updated_at.astimezone(timezone.utc)
    if location_updated_at < now - timedelta(minutes=2):
        raise HTTPException(status_code=409, detail="Update your live location before responding")
    if (
        _distance_km(
            location.latitude,
            location.longitude,
            ride.pickup_latitude,
            ride.pickup_longitude,
        )
        > _dispatch_radius_km()
    ):
        raise HTTPException(status_code=409, detail="Ride is outside your dispatch area")

    if decision.accept:
        ride.driver_id = driver.id
        ride.status = "accepted"
        ride.accepted_at = datetime.now(timezone.utc)
    else:
        db.add(RideDecline(ride_id=ride.id, driver_id=driver.id))

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ride decision was already recorded") from exc
    db.refresh(ride)
    return _public_ride(ride)


@router.patch("/rides/{ride_id}/status", response_model=RidePublic)
def update_ride_status(
    ride_id: int,
    update: RideStatusUpdate,
    db: Session = Depends(get_db),
    driver: User = Depends(driver_only),
) -> RidePublic:
    ride = db.scalar(
        select(Ride).where(Ride.id == ride_id).with_for_update()
    )
    if ride is None or ride.driver_id != driver.id:
        raise HTTPException(status_code=404, detail="Ride not found")

    now = datetime.now(timezone.utc)
    if update.status == "in_transit" and ride.status == "accepted":
        ride.status = "in_transit"
        ride.started_at = now
    elif update.status == "completed" and ride.status == "in_transit":
        ride.status = "completed"
        ride.completed_at = now
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot transition ride from {ride.status} to {update.status}",
        )

    db.commit()
    db.refresh(ride)
    return _public_ride(ride)
