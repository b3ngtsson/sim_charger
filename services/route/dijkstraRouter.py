# Standard library imports
import heapq
import logging
from typing import List, Dict, Tuple, Optional

# Local module imports
from services.chargers.getChargingStations import get_charging_stations
from services.route.getRoadRoute import get_road_route
from services.route.haversine import haversine
from services.soc.simulateSoc import simulate_soc

logger = logging.getLogger(__name__)

class EVRouter:
    """
    Router for electric vehicles that finds optimal routes with charging stops
    
    Uses a modified Dijkstra's algorithm to find the optimal route
    that minimizes total journey time including charging stops.
    """
    
    def __init__(self, start: List[str], end: List[str], initial_soc: float, 
                 battery_capacity: float, energy_consumption: float, 
                 min_kw: int, max_kw: int, avg_speed: float):
        """
        Initialize the EV router
        
        Args:
            start: Starting coordinates [lat, lon]
            end: Destination coordinates [lat, lon]
            initial_soc: Initial state of charge as percentage
            battery_capacity: Battery capacity in kWh
            energy_consumption: Energy consumption in kWh per km
            min_kw: Minimum charging power in kW
            max_kw: Maximum charging power in kW
            avg_speed: Average speed in km/h
        """
        self.start = start
        self.end = end
        self.initial_soc = initial_soc
        self.battery_capacity = battery_capacity
        self.energy_consumption = energy_consumption
        self.min_kw = min_kw
        self.max_kw = max_kw
        self.avg_speed = avg_speed
        self.chargers_cache = {}  # Cache charger data to avoid repeated API calls
        
    def find_optimal_route(self) -> Optional[Dict]:
        """
        Find the optimal route with charging stops using a modified Dijkstra's algorithm
        
        Returns:
            Dictionary with route details including segments, SOC values, and charging stops,
            or None if no route is found
        """
        # Priority queue: (total_time, current_location, current_soc, path, charging_stops)
        queue = [(0, self.start, self.initial_soc, [self.start], [])]
        visited = set()  # Track visited locations with their SOC levels
        
        logger.info("Finding optimal route...")
        while queue:
            total_time, current, soc, path, stops = heapq.heappop(queue)
            
            logger.debug(f"Exploring node - total_time: {total_time}, current: {current}")

            # Skip if we've already visited this node with better soc
            location_key = "{:.4f},{:.4f}".format(float(current[0]), float(current[1]))
            if location_key in visited:
                continue
                
            visited.add(location_key)
            
            # Check if we've reached the destination
            if self.is_destination(current):
                return self.construct_final_route(path, stops)
            
            # Try going directly to destination
            if self.can_reach_destination(current, soc):
                try:
                    direct_route = get_road_route(current, self.end)
                    direct_time = self.calculate_drive_time(direct_route)
                    total_path = path + [self.end]
                    heapq.heappush(queue, (total_time + direct_time, self.end, 0, total_path, stops))
                except Exception as e:
                    logger.error(f"Error calculating direct route to destination: {str(e)}")
            
            # Find nearby charging stations
            try:
                nearby_chargers = self.get_nearby_chargers(current)
                
                for charger in nearby_chargers:
                    charger_location = charger["location"]
                    charger_key = f"{charger_location[0]:.4f},{charger_location[1]:.4f}"
                    
                    # Skip if we've already visited this charger
                    if charger_key in visited:
                        continue
                    
                    # Check if we can reach this charger
                    route_to_charger = get_road_route(current, charger_location)
                    drive_time = self.calculate_drive_time(route_to_charger)
                    
                    # Calculate energy consumed and remaining SOC
                    distance = sum(haversine(route_to_charger[i], route_to_charger[i+1]) 
                                  for i in range(len(route_to_charger)-1))
                    energy_used = distance * self.energy_consumption
                    soc_after_drive = soc - (energy_used / self.battery_capacity) * 100
                    
                    if soc_after_drive > 10:  # Ensure we have at least 10% SOC when arriving
                        # Calculate charging time (charge to 80% for efficiency)
                        target_soc = 80
                        soc_to_add = target_soc - soc_after_drive
                        if soc_to_add > 0:
                            energy_to_add = (soc_to_add / 100) * self.battery_capacity
                            charge_time = (energy_to_add / charger["power"]) * 60  # Minutes
                        else:
                            charge_time = 0
                        
                        new_stop = {
                            "station": charger,
                            "charge_time": charge_time,
                            "charge_amount": soc_to_add if soc_to_add > 0 else 0
                        }
                        
                        new_path = path + [charger_location]
                        new_stops = stops + [new_stop]
                        new_total_time = total_time + drive_time + charge_time

                        heapq.heappush(queue, (new_total_time, charger_location, target_soc, new_path, new_stops))
            except Exception as e:
                logger.error(f"Error processing nearby chargers: {str(e)}")
        
        # If no route is found
        logger.warning("No viable route found")
        return None
    
    def is_destination(self, location: List[str]) -> bool:
        """
        Check if current location is close enough to destination
        
        Args:
            location: Current location coordinates
            
        Returns:
            True if location is within 1km of destination
        """
        return haversine(location, self.end) < 1.0  # Within 1km
    
    def can_reach_destination(self, current: List[str], soc: float) -> bool:
        """
        Check if we can reach destination with current SOC
        
        Args:
            current: Current location coordinates
            soc: Current state of charge
            
        Returns:
            True if vehicle can reach destination with current SOC plus safety margin
        """
        try:
            route = get_road_route(current, self.end)
            distance = sum(haversine(route[i], route[i+1]) for i in range(len(route)-1))
            energy_needed = distance * self.energy_consumption
            soc_needed = (energy_needed / self.battery_capacity) * 100
            return soc >= (soc_needed + 10)  # 10% safety margin
        except Exception as e:
            logger.error(f"Error checking if destination is reachable: {str(e)}")
            return False
    
    def get_nearby_chargers(self, location: List[str]) -> List[Dict]:
        """
        Get nearby charging stations, using cache if available
        
        Args:
            location: Location coordinates to search near
            
        Returns:
            List of charging station dictionaries
        """
        location_key = f"{location[0]:.4f},{location[1]:.4f}"
        if location_key in self.chargers_cache:
            return self.chargers_cache[location_key]
        
        chargers = get_charging_stations(location[0], location[1], 10, self.min_kw, self.max_kw)
        self.chargers_cache[location_key] = chargers
        return chargers
    
    def calculate_drive_time(self, route: List[List[float]]) -> float:
        """
        Calculate driving time in minutes
        
        Args:
            route: List of coordinate points along the route
            
        Returns:
            Estimated driving time in minutes
        """
        distance = sum(haversine(route[i], route[i+1]) for i in range(len(route)-1))
        return (distance / self.avg_speed) * 60
    
    def construct_final_route(self, path: List[List[str]], stops: List[Dict]) -> Dict:
        """
        Construct the final route details
        
        Args:
            path: List of waypoints along the route
            stops: List of charging stops
            
        Returns:
            Dictionary with route details including segments, SOC values, and charging stops
        """
        routes = []
        soc_values = []
        current_soc = self.initial_soc
        
        logger.info(f"Constructing final route with {len(path)} waypoints and {len(stops)} charging stops")
        
        try:
            for i in range(len(path) - 1):
                segment_route = get_road_route(path[i], path[i+1])
                segment_soc = simulate_soc(segment_route, current_soc, self.battery_capacity, self.energy_consumption)
                
                routes.append(segment_route)
                soc_values.append(segment_soc)
                
                # Update SOC after charging if applicable
                if i < len(stops):
                    current_soc = min(segment_soc[-1] + stops[i]["charge_amount"], 100)
            
            # Add final segment to destination if not included
            if path[-1] != self.end:
                final_route = get_road_route(path[-1], self.end)
                final_soc = simulate_soc(final_route, current_soc, self.battery_capacity, self.energy_consumption)
                routes.append(final_route)
                soc_values.append(final_soc)
        
            return {
                "routes": routes,
                "soc_values": soc_values,
                "charging_stops": stops
            }
        except Exception as e:
            logger.error(f"Error constructing final route: {str(e)}")
            raise