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
        distance_fare = 0.0

        for index, drop in enumerate(sorted_drops):
            leg_distance = drop.distance_km - last_distance
            if leg_distance > 0:
                leg_cost = leg_distance * PER_KM_RATE
                distance_fare += leg_cost
                cost_per_head = leg_cost / (len(sorted_drops) - index)
                for passenger in sorted_drops[index:]:
                    fares[passenger.passenger_id] += cost_per_head

            last_distance = drop.distance_km

        total_fare = max(distance_fare, BASE_AUTO_FARE)
        if distance_fare < BASE_AUTO_FARE and fares:
            base_adjustment = (BASE_AUTO_FARE - distance_fare) / len(fares)
            for passenger_id in fares:
                fares[passenger_id] += base_adjustment

        rounded_fares = {
            passenger_id: round(fare, 2) for passenger_id, fare in fares.items()
        }
        rounding_adjustment = round(total_fare - sum(rounded_fares.values()), 2)
        if rounded_fares and rounding_adjustment:
            highest_fare_id = max(rounded_fares, key=rounded_fares.get)
            rounded_fares[highest_fare_id] = round(
                rounded_fares[highest_fare_id] + rounding_adjustment, 2
            )

        return FareSplitResult(
            total_fare=round(total_fare, 2),
            per_passenger_fare=rounded_fares,
            stops=[d.destination for d in sorted_drops],
        )
