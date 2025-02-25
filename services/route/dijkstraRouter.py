
from typing import List, Dict, Tuple
import heapq
from services.route.haversine import haversine
from services.chargers.getChargingStations import get_charging_stations
from services.route.getRoadRoute import get_road_route
from services.soc.simulateSoc import simulate_soc

class EVRouter:
    def __init__(self, start, end, initial_soc, battery_capacity, energy_consumption, min_kw, max_kw, avg_speed):
        self.start = start
        self.end = end
        self.initial_soc = initial_soc
        self.battery_capacity = battery_capacity
        self.energy_consumption = energy_consumption
        self.min_kw = min_kw
        self.max_kw = max_kw
        self.avg_speed = avg_speed
        self.chargers_cache = {}  # Cache charger data to avoid repeated API calls
        
    def find_optimal_route(self):
        """Find the optimal route with charging stops using a modified Dijkstra's algorithm"""
        # Priority queue: (total_time, current_location, current_soc, path, charging_stops)
        queue = [(0, self.start, self.initial_soc, [self.start], [])]
        visited = set()  # Track visited locations with their SOC levels
        
        while queue:
            total_time, current, soc, path, stops = heapq.heappop(queue)
            
            # Skip if we've already visited this node with better soc
            location_key = f"{current[0]:.4f},{current[1]:.4f}"
            if location_key in visited:
                continue
                
            visited.add(location_key)
            
            # Check if we've reached the destination
            if self.is_destination(current):
                return self.construct_final_route(path, stops)
            
            # Try going directly to destination
            if self.can_reach_destination(current, soc):
                direct_route = get_road_route(current, self.end)
                direct_time = self.calculate_drive_time(direct_route)
                total_path = path + [self.end]
                heapq.heappush(queue, (total_time + direct_time, self.end, 0, total_path, stops))
            
            # Find nearby charging stations
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
                distance = sum(haversine(route_to_charger[i], route_to_charger[i+1]) for i in range(len(route_to_charger)-1))
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
        
        # If no route is found
        return None
    
    def is_destination(self, location):
        """Check if current location is close enough to destination"""
        return haversine(location, self.end) < 1.0  # Within 1km
    
    def can_reach_destination(self, current, soc):
        """Check if we can reach destination with current SOC"""
        route = get_road_route(current, self.end)
        distance = sum(haversine(route[i], route[i+1]) for i in range(len(route)-1))
        energy_needed = distance * self.energy_consumption
        soc_needed = (energy_needed / self.battery_capacity) * 100
        return soc >= (soc_needed + 10)  # 10% safety margin
    
    def get_nearby_chargers(self, location):
        """Get nearby charging stations, using cache if available"""
        location_key = f"{location[0]:.4f},{location[1]:.4f}"
        if location_key in self.chargers_cache:
            return self.chargers_cache[location_key]
        
        chargers = get_charging_stations(location[0], location[1], 10, self.min_kw, self.max_kw)
        self.chargers_cache[location_key] = chargers
        return chargers
    
    def calculate_drive_time(self, route):
        """Calculate driving time in minutes"""
        distance = sum(haversine(route[i], route[i+1]) for i in range(len(route)-1))
        return (distance / self.avg_speed) * 60
    
    def construct_final_route(self, path, stops):
        """Construct the final route details"""
        routes = []
        soc_values = []
        current_soc = self.initial_soc
        
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