from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)


class RegisterInput(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    role: Literal["rider", "driver"] = "rider"

    @field_validator("full_name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Full name must contain at least two non-space characters")
        return value


class LoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: Literal["rider", "driver", "admin"]
    is_verified: bool
    is_online: bool


class AuthResponse(BaseModel):
    user: UserPublic


class NaturalLanguageQuery(BaseModel):
    query: str = Field(min_length=3, max_length=1000)

    @field_validator("query")
    @classmethod
    def trim_query(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Describe the ride in at least three characters")
        return value


class ParsedRideIntent(BaseModel):
    pickup: str = Field(min_length=2, max_length=255)
    dropoff: str = Field(min_length=2, max_length=255)
    passenger_count: int = Field(ge=1, le=8)


class VehicleCreate(BaseModel):
    license_plate: str = Field(min_length=3, max_length=24)
    make_model: str = Field(min_length=2, max_length=120)
    capacity: int = Field(ge=1, le=8)

    @field_validator("license_plate")
    @classmethod
    def normalize_plate(cls, value: str) -> str:
        value = value.strip().upper()
        if len(value) < 3:
            raise ValueError("License plate must contain at least three characters")
        return value

    @field_validator("make_model")
    @classmethod
    def trim_model(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Vehicle make/model must contain at least two characters")
        return value


class VehiclePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    license_plate: str
    make_model: str
    capacity: int
    verification_status: Literal["pending", "verified", "rejected"]
    is_active: bool


class DriverStatusInput(BaseModel):
    is_online: bool


class LocationInput(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class NearbyDriver(BaseModel):
    driver_id: int
    full_name: str
    vehicle: str
    capacity: int
    latitude: float
    longitude: float
    distance_km: float


class DriverLocationPublic(BaseModel):
    latitude: float
    longitude: float
    updated_at: datetime


class RideCreate(BaseModel):
    pickup: str = Field(min_length=2, max_length=255)
    dropoff: str = Field(min_length=2, max_length=255)
    passenger_count: int = Field(ge=1, le=8)
    pickup_latitude: float = Field(ge=-90, le=90)
    pickup_longitude: float = Field(ge=-180, le=180)
    dropoff_latitude: float | None = Field(default=None, ge=-90, le=90)
    dropoff_longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def validate_coordinate_pairs(self):
        for latitude, longitude, label in (
            (self.pickup_latitude, self.pickup_longitude, "pickup"),
            (self.dropoff_latitude, self.dropoff_longitude, "dropoff"),
        ):
            if (latitude is None) != (longitude is None):
                raise ValueError(f"{label} latitude and longitude must be provided together")
        return self


class RideDecision(BaseModel):
    accept: bool


class RideStatusUpdate(BaseModel):
    status: Literal["in_transit", "completed"]


class RidePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rider_id: int
    driver_id: int | None
    pickup: str
    dropoff: str
    pickup_latitude: float | None
    pickup_longitude: float | None
    dropoff_latitude: float | None
    dropoff_longitude: float | None
    passenger_count: int
    fare_amount: float
    status: Literal["requested", "accepted", "in_transit", "completed"]


class WaypointDrop(BaseModel):
    passenger_id: str
    destination: str
    distance_km: float = Field(ge=0)


class FareSplitResult(BaseModel):
    total_fare: float
    per_passenger_fare: dict[str, float]
    stops: list[str]
