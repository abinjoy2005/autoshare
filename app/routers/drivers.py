import hmac
import math
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Location, Ride, User, Vehicle
from app.schemas import (
    DriverStatusInput,
    LocationInput,
    NearbyDriver,
    VehicleCreate,
    VehiclePublic,
)
from app.security import require_role

router = APIRouter(prefix="/api", tags=["drivers and locations"])
driver_only = require_role("driver")
rider_only = require_role("rider")
EARTH_RADIUS_KM = 6371.0088


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    delta_lat, delta_lon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(min(1.0, haversine)))


def _has_verified_vehicle(db: Session, driver_id: int) -> bool:
    return (
        db.scalar(
            select(Vehicle.id).where(
                Vehicle.driver_id == driver_id,
                Vehicle.is_active.is_(True),
                Vehicle.verification_status == "verified",
            )
        )
        is not None
    )


@router.post("/drivers/me/vehicles", response_model=VehiclePublic, status_code=201)
def register_vehicle(
    payload: VehicleCreate,
    db: Session = Depends(get_db),
    driver: User = Depends(driver_only),
) -> Vehicle:
    vehicle = Vehicle(
        driver_id=driver.id,
        license_plate=payload.license_plate,
        make_model=payload.make_model.strip(),
        capacity=payload.capacity,
        verification_status="pending",
    )
    db.add(vehicle)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="License plate is already registered") from exc
    db.refresh(vehicle)
    return vehicle


@router.get("/drivers/me/vehicles", response_model=list[VehiclePublic])
def list_my_vehicles(
    db: Session = Depends(get_db),
    driver: User = Depends(driver_only),
) -> list[Vehicle]:
    return list(
        db.scalars(
            select(Vehicle)
            .where(Vehicle.driver_id == driver.id)
            .order_by(Vehicle.created_at.desc())
        )
    )


@router.put("/drivers/me/status")
def set_driver_status(
    payload: DriverStatusInput,
    db: Session = Depends(get_db),
    driver: User = Depends(driver_only),
) -> dict[str, bool]:
    if payload.is_online and (
        not driver.is_verified or not _has_verified_vehicle(db, driver.id)
    ):
        raise HTTPException(
            status_code=403,
            detail="Driver and at least one active vehicle must be verified before going online",
        )
    driver.is_online = payload.is_online
    db.commit()
    return {"is_online": driver.is_online}


@router.put("/drivers/me/location")
def update_location(
    payload: LocationInput,
    db: Session = Depends(get_db),
    driver: User = Depends(driver_only),
) -> dict[str, object]:
    if (
        not driver.is_online
        or not driver.is_verified
        or not _has_verified_vehicle(db, driver.id)
    ):
        raise HTTPException(status_code=409, detail="Driver must be verified and online")
    location = db.scalar(select(Location).where(Location.driver_id == driver.id))
    now = datetime.now(timezone.utc)
    if location is None:
        location = Location(
            driver_id=driver.id,
            latitude=payload.latitude,
            longitude=payload.longitude,
            updated_at=now,
        )
        db.add(location)
    else:
        location.latitude = payload.latitude
        location.longitude = payload.longitude
        location.updated_at = now
    db.commit()
    return {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "updated_at": location.updated_at,
    }


@router.get("/drivers/nearby", response_model=list[NearbyDriver])
def nearby_drivers(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    radius_km: float = Query(default=5, gt=0, le=50),
    passenger_count: int = Query(default=1, ge=1, le=8),
    db: Session = Depends(get_db),
    _: User = Depends(rider_only),
) -> list[NearbyDriver]:
    now = datetime.now(timezone.utc)
    latitude_delta = radius_km / 110.574
    min_lat, max_lat = max(-90, latitude - latitude_delta), min(90, latitude + latitude_delta)
    conditions = [
        User.role == "driver",
        User.is_online.is_(True),
        User.is_verified.is_(True),
        Vehicle.is_active.is_(True),
        Vehicle.verification_status == "verified",
        Vehicle.capacity >= passenger_count,
        Location.updated_at >= now - timedelta(minutes=2),
        Location.latitude.between(min_lat, max_lat),
        ~select(Ride.id)
        .where(
            Ride.driver_id == User.id,
            Ride.status.in_(("accepted", "in_transit")),
        )
        .exists(),
    ]
    longitude_delta = min(
        180,
        radius_km / (111.320 * max(math.cos(math.radians(latitude)), 0.01)),
    )
    if longitude_delta < 180:
        min_lon, max_lon = longitude - longitude_delta, longitude + longitude_delta
        if min_lon < -180:
            conditions.append(
                or_(Location.longitude >= min_lon + 360, Location.longitude <= max_lon)
            )
        elif max_lon > 180:
            conditions.append(
                or_(Location.longitude >= min_lon, Location.longitude <= max_lon - 360)
            )
        else:
            conditions.append(Location.longitude.between(min_lon, max_lon))

    rows = db.execute(
        select(User, Vehicle, Location)
        .join(Vehicle, Vehicle.driver_id == User.id)
        .join(Location, Location.driver_id == User.id)
        .where(and_(*conditions))
        .order_by(Location.updated_at.desc())
        .limit(250)
    ).all()
    results: dict[int, NearbyDriver] = {}
    for user, vehicle, location in rows:
        distance = _distance_km(
            latitude, longitude, location.latitude, location.longitude
        )
        if distance <= radius_km and (
            user.id not in results or vehicle.capacity > results[user.id].capacity
        ):
            results[user.id] = NearbyDriver(
                driver_id=user.id,
                full_name=user.full_name,
                vehicle=vehicle.make_model,
                capacity=vehicle.capacity,
                latitude=location.latitude,
                longitude=location.longitude,
                distance_km=round(distance, 2),
            )
    return sorted(results.values(), key=lambda item: item.distance_km)


@router.post("/admin/drivers/{driver_id}/vehicles/{vehicle_id}/verify")
def verify_driver_vehicle(
    driver_id: int,
    vehicle_id: int,
    verified: bool = Query(...),
    x_admin_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    expected_key = os.getenv("ADMIN_API_KEY")
    if not expected_key or len(expected_key) < 32:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_API_KEY must be configured with at least 32 characters",
        )
    if not x_admin_api_key or not hmac.compare_digest(x_admin_api_key, expected_key):
        raise HTTPException(status_code=403, detail="Administrator authorization failed")

    driver = db.get(User, driver_id)
    vehicle = db.get(Vehicle, vehicle_id)
    if driver is None or driver.role != "driver" or vehicle is None or vehicle.driver_id != driver_id:
        raise HTTPException(status_code=404, detail="Driver or vehicle not found")

    vehicle.verification_status = "verified" if verified else "rejected"
    driver.is_verified = verified or _has_verified_vehicle(
        db, driver_id
    )
    if not driver.is_verified:
        driver.is_online = False
    db.commit()
    return {"verification_status": vehicle.verification_status}
