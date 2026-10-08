import hmac
import json
import logging
import os
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from google import genai
from pydantic import Field

from app.engine import FareSplitter
from app.models import User
from app.routers import auth, drivers, rides
from app.schemas import NaturalLanguageQuery, ParsedRideIntent, UserPublic, WaypointDrop
from app.security import get_current_user, require_role

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent.parent
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]


app = FastAPI(title="AutoShare", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "X-Admin-API-Key"],
)

app.include_router(auth.router)
app.include_router(drivers.router)
app.include_router(rides.router)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/api/setup-db")
def setup_db_page():
    from fastapi.responses import FileResponse

    return FileResponse(BASE_DIR / "static" / "setup-db.html")


@app.post("/api/setup-db")
def setup_db(x_admin_api_key: str | None = Header(default=None)) -> dict[str, str]:
    expected_key = os.getenv("ADMIN_API_KEY")
    if not expected_key or len(expected_key) < 32:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_API_KEY must be configured with at least 32 characters",
        )
    if not x_admin_api_key or not hmac.compare_digest(x_admin_api_key, expected_key):
        raise HTTPException(status_code=403, detail="Administrator authorization failed")

    from app.database import Base, engine

    Base.metadata.create_all(bind=engine)
    return {"message": "Database tables created successfully"}


def parse_ride_prompt(query: str) -> dict[str, object]:
    if client is None:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY is not configured")
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=query,
            config={
                "response_mime_type": "application/json",
                "response_schema": ParsedRideIntent,
            },
        )
        if not response.text:
            raise ValueError("Gemini returned an empty response")
        result = ParsedRideIntent.model_validate(json.loads(response.text))
        return result.model_dump()
    except (genai.errors.APIError, ValueError, TypeError) as exc:
        logger.exception("Ride intent extraction failed")
        raise HTTPException(
            status_code=502, detail="Ride intent could not be extracted"
        ) from exc


@app.post("/api/parse-ride", response_model=ParsedRideIntent)
def parse_ride(
    payload: NaturalLanguageQuery,
    _: User = Depends(require_role("rider")),
):
    return parse_ride_prompt(payload.query)


@app.get("/api/me", response_model=UserPublic)
def current_user(user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(user)


@app.post("/api/split-fare")
async def calculate_split(
    drops: Annotated[list[WaypointDrop], Field(min_length=1, max_length=8)],
):
    passenger_ids = [drop.passenger_id for drop in drops]
    if len(set(passenger_ids)) != len(passenger_ids):
        raise HTTPException(status_code=422, detail="Passenger IDs must be unique")
    return FareSplitter.calculate_waypoint_split(drops)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def index():
    from fastapi.responses import FileResponse

    return FileResponse(BASE_DIR / "static" / "index.html")