from typing import Dict, List

from services.route.haversine import haversine

def calculate_total_time(routes: List[List[List[float]]], charging_stops: List[Dict], speed: float) -> float:
   def calculate_total_time(routes, charging_stops, avg_speed):
    """
    Calculate total journey time including driving and charging
    
    Args:
        routes: List of route segments
        charging_stops: List of charging stop details
        avg_speed: Average driving speed in km/h
        
    Returns:
        Total time in minutes
    """
    # Calculate driving time
    total_driving_time = 0
    for route in routes:
        distance = sum(haversine(route[i], route[i+1]) for i in range(len(route)-1))
        segment_time = (distance / avg_speed) * 60  # Convert to minutes
        total_driving_time += segment_time
    
    # Add charging time
    total_charging_time = sum(stop["charge_time"] for stop in charging_stops)
    
    # Add a small buffer for each stop (parking, plugging in, etc.)
    buffer_time = len(charging_stops) * 5  # 5 minutes per stop
    
    return total_driving_time + total_charging_time + buffer_time
