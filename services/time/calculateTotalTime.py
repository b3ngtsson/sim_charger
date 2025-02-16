from typing import Dict, List

from services.route.haversine import haversine

def calculate_total_time(routes: List[List[List[float]]], charging_stops: List[Dict], speed: float) -> float:
    """Calculate total travel time (driving + charging)"""
    total_time = 0
    for route in routes:
        distance = sum(haversine(route[i], route[i+1]) for i in range(len(route)-1))
        total_time += (distance / speed) * 60
    for stop in charging_stops:
        total_time += stop["charge_time"]
    return total_time
