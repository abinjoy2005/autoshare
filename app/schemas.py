from pydantic import AliasChoices, BaseModel, Field
from typing import List

class NaturalLanguageQuery(BaseModel):
    query: str = Field(
        ...,
        validation_alias=AliasChoices("query", "prompt"),
        example="Need an auto to Angamaly railway station for 2 people in 10 mins",
    )

class ParsedRideIntent(BaseModel):
    origin: str = "Campus Gate"
    destination: str
    passenger_count: int
    departure_in_minutes: int
    raw_query: str


class RideRequestCreate(BaseModel):
    origin: str = Field(default="Campus Gate", min_length=1, max_length=255)
    destination: str = Field(..., min_length=1, max_length=255)
    passenger_count: int = Field(default=1, ge=1, le=3)
    departure_in_minutes: int = Field(default=5, ge=0)


class WaypointDrop(BaseModel):
    passenger_id: str
    destination: str
    distance_km: float

class FareSplitResult(BaseModel):
    total_fare: float
    per_passenger_fare: dict[str, float]
    stops: List[str]

class RideGroup(BaseModel):
    group_id: str
    origin: str
    destination: str
    current_passengers: int
    max_passengers: int = 3
    departure_timestamp: float
    is_urgent: bool = False