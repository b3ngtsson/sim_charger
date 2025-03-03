# Standard library imports
import logging
import math
from typing import Dict, List, Optional

# Local module imports
from services.chargers.getChargingStations import get_charging_stations
from services.route.getRoadRoute import get_road_route
from services.route.haversine import haversine

logger = logging.getLogger(__name__)

def find_charging_stop(route: List[List[float]], soc_values: List[float], battery_capacity: float, 
                       energy_consumption: float, min_kw: int, max_kw: int, speed: float) -> Optional[Dict]:
    """
    Find optimal charging station along the route with improved station selection
    
    Args:
        route: List of coordinate points along the route
        soc_values: List of state of charge values at each point
        battery_capacity: Battery capacity in kWh
        energy_consumption: Energy consumption in kWh per km
        min_kw: Minimum charging power in kW
        max_kw: Maximum charging power in kW
        speed: Average speed in km/h
        
    Returns:
        Dictionary with charging station details or None if no suitable station found
    """
    # Track distance traveled to check every 10km
    distance_traveled = 0
    last_check_distance = 0
    
    for i, (point, soc) in enumerate(zip(route, soc_values)):
        # Calculate distance traveled so far
        if i > 0:
            distance_traveled += haversine(route[i-1], point)
        
        # Check for charging stations every 30km or if SOC is critically low
        check_distance = 30  # km
        if soc < 15:  # Critical SOC, check more frequently
            check_distance = 5  # km
            
        # Only check if we've traveled at least check_distance km since last check
        if (distance_traveled - last_check_distance) >= check_distance or soc < 15:
            logger.debug(f"distance: {distance_traveled - last_check_distance}")
            logger.debug(f"check_distance: {check_distance}")
            logger.debug(f"soc: {soc}")
            last_check_distance = distance_traveled
            remaining_distance = sum(haversine(route[j], route[j+1]) for j in range(i, len(route)-1))
            energy_needed = remaining_distance * energy_consumption
            soc_needed = (energy_needed / battery_capacity) * 100

            # If we have enough SOC to reach destination with buffer, continue
            if soc >= (soc_needed + 15):
                continue

            # Calculate ideal charging location - look further ahead on the route
            # based on current SOC and consumption rate
            distance_to_search = (soc - 15) / 100 * battery_capacity / energy_consumption
            logger.debug(f"distance to search {distance_to_search}")
            search_points = []
            
            # Get multiple potential search points along the route
            current_dist = 0
            search_index = i
            
            search_points.append(route[i])
            # Find points at regular intervals within our range
            """ while current_dist < distance_to_search and search_index < len(route) - 1:
                if current_dist > 0 and current_dist % 30:  # Every ~10km
                    logger.debug(f"current dist 1 : {search_index}")
                    search_points.append(route[search_index])
                
                if search_index + 1 < len(route):
                    current_dist += haversine(route[search_index], route[search_index+1])
                    logger.debug(f"current dist 2 : {current_dist}")
                search_index += 1
             """
            logger.debug(f"search_index length: {len(search_points)}")
            # If no search points found within our range, use the furthest possible point
            if not search_points and search_index < len(route):
                search_points.append(route[search_index])
            
            # Find stations near all search points
            all_stations = []
            for search_point in search_points:
                logger.debug(f"search_point {search_point}")
                nearby_stations = get_charging_stations(search_point[0], search_point[1], 10, min_kw, max_kw)
                for station in nearby_stations:

                    # Calculate detour factors
                    detour_route = get_road_route(point, station["location"])
                    detour_distance = sum(haversine(detour_route[j], detour_route[j+1]) 
                                         for j in range(len(detour_route)-1))
                    detour_time = (detour_distance / speed) * 60

                    # Calculate time to charge
                    energy_used_detour = detour_distance * energy_consumption
                    soc_after_detour = soc - (energy_used_detour / battery_capacity) * 100
                    soc_after_detour = max(soc_after_detour, 0)
                    
                    required_soc = min(80, soc_needed + 15)  # Charge to 80% or what's needed + buffer
                    charge_amount = max(required_soc - soc_after_detour, 10)
                    charge_amount = min(charge_amount, 100 - soc_after_detour)
                    
                    energy_needed = (charge_amount / 100) * battery_capacity
                    charge_time = (energy_needed / station["power"]) * 60
                    
                    # Calculate efficiency score (lower is better)
                    # Balance between: detour time, charging time, and remaining route positioning
                    route_to_destination = get_road_route(station["location"], route[-1])
                    remaining_route_length = sum(haversine(route_to_destination[j], route_to_destination[j+1])
                                               for j in range(len(route_to_destination)-1))
                    
                    # Penalty for stations that take us far from our route
                    proximity_to_route = min([haversine(station["location"], r) for r in route[i:min(i+100, len(route))]])
                    route_deviation_penalty = proximity_to_route * 2
                    
                    # Time efficiency score - balance detour time and charging time
                    time_efficiency = detour_time + charge_time + route_deviation_penalty
                    logger.debug(f"time_efficiency: {time_efficiency}")
                    # Ensure we can reach this station with current SOC
                    if soc_after_detour > 10:
                        all_stations.append({
                            "station": station,
                            "charge_time": charge_time,
                            "detour_time": detour_time,
                            "route_index": i,
                            "charge_amount": charge_amount,
                            "efficiency_score": time_efficiency,
                            "remaining_distance": remaining_route_length
                        })
            
            # Sort by efficiency score and return the best station
            logger.debug(f"all_stations: {all_stations}")
            if all_stations:
                # Sort by efficiency (lower is better)
                best_station = min(all_stations, key=lambda x: x["efficiency_score"])
                return best_station

          
    return None

def plan_multiple_charging_stops(route: List[List[float]], initial_soc: float, battery_capacity: float,
                              energy_consumption: float, min_kw: int, max_kw: int, speed: float) -> List[Dict]:
    """
    Plan multiple charging stops for the entire route at once
    
    Args:
        route: List of coordinate points along the route
        initial_soc: Initial state of charge as percentage
        battery_capacity: Battery capacity in kWh
        energy_consumption: Energy consumption in kWh per km
        min_kw: Minimum charging power in kW
        max_kw: Maximum charging power in kW
        speed: Average speed in km/h
        
    Returns:
        List of dictionaries with charging stop details
    """
    total_distance = sum(haversine(route[i], route[i+1]) for i in range(len(route)-1))
    total_energy = total_distance * energy_consumption
    
    # If we can make it with the initial charge, no stops needed
    if (initial_soc / 100) * battery_capacity >= (total_energy + 0.1 * battery_capacity):
        return []
    
    # Break the route into segments of ~100km for analysis points
    segment_length = 100  # km
    num_segments = math.ceil(total_distance / segment_length)
    segments = []
    
    current_distance = 0
    segment_start_idx = 0
    
    for i in range(len(route)-1):
        distance = haversine(route[i], route[i+1])
        current_distance += distance
        
        if current_distance >= segment_length or i == len(route)-2:
            segments.append({
                "start_idx": segment_start_idx,
                "end_idx": i+1,
                "distance": current_distance,
                "coordinates": route[segment_start_idx:i+2]
            })
            current_distance = 0
            segment_start_idx = i+1
    
    # Simulate consumption along the route
    soc_values = [initial_soc]
    current_soc = initial_soc
    
    for i in range(len(route)-1):
        distance = haversine(route[i], route[i+1])
        energy_used = distance * energy_consumption
        soc_drop = (energy_used / battery_capacity) * 100
        current_soc -= soc_drop
        current_soc = max(current_soc, 0)
        soc_values.append(current_soc)
    
    # Identify critical points where we need to charge
    charging_stops = []
    critical_segments = []
    
    for i, segment in enumerate(segments):
        min_soc_in_segment = min(soc_values[segment["start_idx"]:segment["end_idx"]+1])
        
        # If SOC drops below 20% in this segment, mark it as critical
        if min_soc_in_segment < 20:
            critical_segments.append(i)
    
    # For each critical segment, find a charging station before it
    current_soc = initial_soc
    processed_distance = 0
    
    for i in range(len(segments)):
        segment = segments[i]
        
        # If this is a critical segment or the next one is, find a charging station
        if i in critical_segments or (i+1 < len(segments) and i+1 in critical_segments):
            # Find a charging point in the previous or current segment
            search_segment = segments[max(0, i-1)] if i > 0 else segment
            
            # Find charging stations near the middle of the search segment
            mid_idx = (search_segment["start_idx"] + search_segment["end_idx"]) // 2
            mid_point = route[mid_idx]
            
            # Get stations within 15km
            stations = get_charging_stations(mid_point[0], mid_point[1], 15, min_kw, max_kw)
            
            if stations:
                # Choose the station with highest power for efficiency
                best_station = max(stations, key=lambda x: x["power"])
                
                # Calculate route details to this station
                route_to_station = get_road_route(route[search_segment["start_idx"]], best_station["location"])
                station_distance = sum(haversine(route_to_station[j], route_to_station[j+1]) 
                                    for j in range(len(route_to_station)-1))
                
                # Calculate energy used and SOC after reaching the station
                energy_to_station = station_distance * energy_consumption
                soc_at_station = current_soc - (energy_to_station / battery_capacity) * 100
                soc_at_station = max(soc_at_station, 0)
                
                # Charge amount needed (charge to 80% for efficiency)
                charge_amount = 80 - soc_at_station
                charge_amount = max(charge_amount, 10)  # At least 10% charge
                
                # Calculate charging time
                energy_to_add = (charge_amount / 100) * battery_capacity
                charge_time = (energy_to_add / best_station["power"]) * 60  # Minutes
                
                # Add stop to our plan
                charging_stops.append({
                    "station": best_station,
                    "charge_time": charge_time,
                    "detour_time": 0,  # This needs to be calculated from the main route
                    "route_index": search_segment["start_idx"],
                    "charge_amount": charge_amount
                })
                
                # Update current SOC after charging
                current_soc = soc_at_station + charge_amount
        
        # Update the SOC after this segment
        segment_distance = segment["distance"]
        energy_used = segment_distance * energy_consumption
        soc_used = (energy_used / battery_capacity) * 100
        current_soc -= soc_used
        current_soc = max(current_soc, 0)
        
        processed_distance += segment_distance
    
    return charging_stops