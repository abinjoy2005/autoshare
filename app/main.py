from contextlib import asynccontextmanager
import json
import logging
import os

import google.generativeai as genai
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from google.api_core.exceptions import GoogleAPIError
from sqlalchemy.orm import Session

from app.database import get_db, init_db
from app.schemas import (
    NaturalLanguageQuery,
    ParsedRideIntent,
    RideRequestCreate,
    WaypointDrop,
)
from app.engine import FareSplitter, MatchingEngine
from app.websocket_manager import ConnectionManager

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

logger = logging.getLogger(__name__)
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")
    if origin.strip()
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="AutoShare Engine", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = ConnectionManager()
matching_engine = MatchingEngine()

app.mount("/static", StaticFiles(directory="static"), name="static")


def parse_ride_prompt(query: str) -> dict:
    if not os.getenv("GEMINI_API_KEY"):
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY is not configured")
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(
            query,
            generation_config={
                "response_mime_type": "application/json",
                "response_schema": ParsedRideIntent,
            },
        )
        return json.loads(response.text)
    except (GoogleAPIError, ValueError, TypeError, KeyError) as exc:
        logger.exception("Ride intent extraction failed")
        raise HTTPException(
            status_code=502, detail="Ride intent could not be extracted"
        ) from exc


@app.post("/api/parse-ride", response_model=ParsedRideIntent)
def parse_ride(payload: NaturalLanguageQuery):
    return parse_ride_prompt(payload.query)


@app.post("/api/ride-requests")
def create_ride_request(
    payload: RideRequestCreate,
    db: Session = Depends(get_db),
):
    result = matching_engine.add_request(db, payload)
    db.commit()
    return result

@app.post("/api/split-fare")
async def calculate_split(drops: list[WaypointDrop]):
    return FareSplitter.calculate_waypoint_split(drops)

@app.websocket("/ws/cursors")
async def websocket_cursor_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await manager.broadcast(data, websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)