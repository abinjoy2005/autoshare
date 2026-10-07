from datetime import datetime, timedelta, timezone
from typing import Dict, List

from sqlalchemy.orm import Session

from app.models import ActiveRideGroup, RideRequest
from app.schemas import FareSplitResult, RideRequestCreate, WaypointDrop

BASE_AUTO_FARE = 30.0
PER_KM_RATE = 15.0

class FareSplitter:
    @staticmethod
    def calculate_waypoint_split(drops: List[WaypointDrop]) -> FareSplitResult:
        sorted_drops = sorted(drops, key=lambda d: d.distance_km)
        fares: Dict[str, float] = {d.passenger_id: 0.0 for d in sorted_drops}
        
        last_distance = 0.0
        remaining_passengers = len(sorted_drops)
        total_fare = 0.0

        for drop in sorted_drops:
            leg_distance = drop.distance_km - last_distance
            if leg_distance > 0:
                leg_cost = leg_distance * PER_KM_RATE
                total_fare += leg_cost
                cost_per_head = leg_cost / remaining_passengers
                for rider_id in fares:
                    fares[rider_id] += cost_per_head
            
            last_distance = drop.distance_km
            remaining_passengers -= 1

        total_fare = max(total_fare, BASE_AUTO_FARE)
        for rider_id in fares:
            fares[rider_id] = round(max(fares[rider_id], BASE_AUTO_FARE / len(sorted_drops)), 2)

        return FareSplitResult(
            total_fare=round(total_fare, 2),
            per_passenger_fare=fares,
            stops=[d.destination for d in sorted_drops]
        )

class MatchingEngine:
    def add_request(self, db: Session, request_data: RideRequestCreate) -> dict:
        request = RideRequest(
            origin=request_data.origin,
            destination=request_data.destination,
            passenger_count=request_data.passenger_count,
            departure_at=datetime.now(timezone.utc)
            + timedelta(minutes=request_data.departure_in_minutes),
        )
        db.add(request)
        db.flush()

        candidates = (
            db.query(RideRequest)
            .filter(
                RideRequest.status == "queued",
                RideRequest.origin == request.origin,
                RideRequest.destination == request.destination,
                RideRequest.id != request.id,
            )
            .order_by(RideRequest.created_at, RideRequest.id)
            .all()
        )
        matched_requests = [request]
        total_seats = request.passenger_count

        for candidate in candidates:
            if total_seats + candidate.passenger_count <= 3:
                matched_requests.append(candidate)
                total_seats += candidate.passenger_count
                if total_seats >= 2:
                    break

        if total_seats >= 2:
            departure_times = [
                member.departure_at.replace(tzinfo=timezone.utc)
                if member.departure_at.tzinfo is None
                else member.departure_at.astimezone(timezone.utc)
                for member in matched_requests
            ]
            group = ActiveRideGroup(
                origin=request.origin,
                destination=request.destination,
                current_passengers=total_seats,
                max_passengers=3,
                status="urgent" if total_seats == 2 else "ready",
                departure_at=min(departure_times),
            )
            db.add(group)
            db.flush()

            for member in matched_requests:
                member.group = group
                member.status = "matched"

            db.flush()
            return {
                "group_id": f"ride_{group.id}",
                "passengers": group.current_passengers,
                "max_seats": group.max_passengers,
                "status": group.status,
                "members": [
                    {
                        "request_id": member.id,
                        "passengers": member.passenger_count,
                        "origin": member.origin,
                        "destination": member.destination,
                    }
                    for member in matched_requests
                ],
            }

        frontier_size = (
            db.query(RideRequest)
            .filter(RideRequest.status == "queued")
            .count()
        )
        return {"status": "queued", "frontier_size": frontier_size}