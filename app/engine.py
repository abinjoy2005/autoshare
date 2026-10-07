from typing import Dict, List

from app.schemas import FareSplitResult, WaypointDrop

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
