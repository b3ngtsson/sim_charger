from flask import Flask, request, jsonify
import folium
import requests

from services.map.generateMap import create_map
from services.route.getRoadRoute import get_road_route, get_road_route_with_waypoints
from services.route.haversine import haversine
from services.chargers.getChargingStations import get_charging_stations
from services.chargers.findChargingStations import find_charging_stop, plan_multiple_charging_stops
from services.soc.simulateSoc import simulate_soc
from services.time.calculateTotalTime import calculate_total_time

app = Flask(__name__)

# Constants
ENERGY_CONSUMPTION = 0.2  # kWh per km
AVG_SPEED = 90  # km/h

@app.route('/calculate', methods=['POST'])
def calculate_route():
    """Main endpoint for calculating EV routes"""
    data = request.get_json()
    
    # Get the routing strategy from request or default to 'standard'
    strategy = data.get('routingStrategy', 'standard')
    
    try:
        if strategy == 'standard':
            return standard_route_planning(data)
        elif strategy == 'optimized_waypoints':
            return optimized_waypoints_routing(data)
        elif strategy == 'dijkstra':
            return dijkstra_route_planning(data)
        elif strategy == 'time_efficient':
            return time_efficient_route(data)
        else:
            return {"error": f"Unknown routing strategy: {strategy}"}, 400
    
    except Exception as e:
        print(f"Error calculating route: {str(e)}")
        return {"error": str(e)}, 400

def optimized_waypoints_routing():
    """Calculate route with optimized waypoints using OSRM"""
    data = request.get_json()
    
    try:
        start = data["start"].split(",")
        end = data["end"].split(",")
        min_kw = data["minKw"]
        max_kw = data["maxKw"]
        battery_capacity = float(data['battery'])
        initial_soc = float(data.get('soc', 80))
        
        MIN_KW = min_kw
        MAX_KW = max_kw
        
        # Get direct route first to estimate energy needs
        direct_route = get_road_route(start, end)
        soc_values = simulate_soc(direct_route, initial_soc, battery_capacity, ENERGY_CONSUMPTION)
        
        # If we can make it without charging, return the direct route
        if min(soc_values) > 10:  # 10% safety buffer
            map_html = create_map([direct_route], [soc_values], [], start, end, AVG_SPEED)
            return {
                "map_html": map_html,
                "total_time": (len(direct_route) / AVG_SPEED) * 60,  # Estimate time in minutes
                "charging_stops": []
            }
        
        # Find multiple charging stops for the journey using the improved algorithm
        charging_stops = plan_multiple_charging_stops(
            direct_route, initial_soc, battery_capacity, 
            ENERGY_CONSUMPTION, MIN_KW, MAX_KW, AVG_SPEED
        )
        
        if not charging_stops:
            raise Exception("Could not find suitable charging stops for this journey")
        
        # Create waypoints list: start -> charging stops -> end
        waypoints = [start]
        for stop in charging_stops:
            waypoints.append(stop["station"]["location"])
        waypoints.append(end)
        
        # Get optimized route through all waypoints
        full_route_data = get_road_route_with_waypoints(waypoints)
        full_route = full_route_data["route"]
        waypoint_indices = full_route_data["waypoint_indices"]
        
        # Break route into segments between waypoints
        route_segments = []
        for i in range(len(waypoint_indices) - 1):
            start_idx = waypoint_indices[i]
            end_idx = waypoint_indices[i + 1]
            segment = full_route[start_idx:end_idx + 1]
            route_segments.append(segment)
        
        # Simulate SOC for each segment
        soc_values_segments = []
        current_soc = initial_soc
        
        for i, segment in enumerate(route_segments):
            segment_soc = simulate_soc(segment, current_soc, battery_capacity, ENERGY_CONSUMPTION)
            soc_values_segments.append(segment_soc)
            
            # Update SOC after charging (if not the final segment)
            if i < len(charging_stops):
                current_soc = min(segment_soc[-1] + charging_stops[i]["charge_amount"], 100)
        
        # Calculate total journey time including driving and charging
        total_drive_time = full_route_data["duration"]  # Already in minutes
        total_charge_time = sum(stop["charge_time"] for stop in charging_stops)
        total_time = total_drive_time + total_charge_time
        
        # Generate map visualization
        map_html = create_map(route_segments, soc_values_segments, charging_stops, start, end, AVG_SPEED)
        
        return {
            "map_html": map_html,
            "total_time": total_time,
            "charging_stops": charging_stops,
            "total_distance": full_route_data["distance"]
        }
    
    except Exception as e:
        print(f"Error in optimized routing: {str(e)}")
        return {"error": str(e)}, 400
    
def standard_route_planning(data):
    """
    Basic route planning with sequential charging stops.
    This is the original algorithm with improvements.
    """
    try:
        start = data["start"].split(",")
        end = data["end"].split(",")
        min_kw = data["minKw"]
        max_kw = data["maxKw"]
        battery_capacity = float(data['battery'])
        initial_soc = float(data.get('soc', 80))
        
        MIN_KW = min_kw
        MAX_KW = max_kw
        
        # Get direct route first
        direct_route = get_road_route(start, end)
        soc_values = simulate_soc(direct_route, initial_soc, battery_capacity, ENERGY_CONSUMPTION)
        
        # Identify all needed charging stops
        potential_stops = []
        temp_route = direct_route
        temp_soc = initial_soc
        temp_soc_values = soc_values
        
        while True:
            charging_stop = find_charging_stop(
                temp_route, temp_soc_values, battery_capacity, 
                ENERGY_CONSUMPTION, MIN_KW, MAX_KW, AVG_SPEED
            )
            
            if not charging_stop:
                break
                
            potential_stops.append(charging_stop)
            
            # Calculate SOC after charging
            route_to_charger = temp_route[:charging_stop["route_index"] + 1]
            if len(route_to_charger) > 0:
                route_to_charger += get_road_route(
                    temp_route[charging_stop["route_index"]], 
                    charging_stop["station"]["location"]
                )
            else:
                route_to_charger = get_road_route(
                    temp_route[0], 
                    charging_stop["station"]["location"]
                )
                
            temp_soc_to_charger = simulate_soc(route_to_charger, temp_soc, battery_capacity, ENERGY_CONSUMPTION)
            temp_soc = min(temp_soc_to_charger[-1] + charging_stop["charge_amount"], 100)
            
            # Get remaining route from charger to destination
            route_from_charger = get_road_route(charging_stop["station"]["location"], end)
            temp_soc_values = simulate_soc(route_from_charger, temp_soc, battery_capacity, ENERGY_CONSUMPTION)
            
            temp_route = route_from_charger
        
        # Generate optimized route with all charging stops
        if potential_stops:
            # Create waypoints list
            waypoints = [start]
            for stop in potential_stops:
                waypoints.append(stop["station"]["location"])
            waypoints.append(end)
            
            # Create routes between consecutive waypoints
            routes = []
            soc_values_full = []
            current_soc = initial_soc
            
            for i in range(len(waypoints) - 1):
                segment_route = get_road_route(waypoints[i], waypoints[i+1])
                segment_soc = simulate_soc(segment_route, current_soc, battery_capacity, ENERGY_CONSUMPTION)
                
                routes.append(segment_route)
                soc_values_full.append(segment_soc)
                
                # Update SOC after charging
                if i < len(potential_stops):
                    current_soc = min(segment_soc[-1] + potential_stops[i]["charge_amount"], 100)
            
            charging_stops = potential_stops
        else:
            # No charging stops needed
            routes = [direct_route]
            soc_values_full = [soc_values]
            charging_stops = []
        
        # Calculate total journey time
        total_time = calculate_total_time(routes, charging_stops, AVG_SPEED)
        
        # Generate map visualization
        map_html = create_map(routes, soc_values_full, charging_stops, start, end, AVG_SPEED)
        
        return {
            "map_html": map_html,
            "total_time": total_time,
            "charging_stops": charging_stops
        }
    
    except Exception as e:
        print(f"Error in standard route planning: {str(e)}")
        return {"error": str(e)}, 400

def dijkstra_route_planning(data):
    """
    Use Dijkstra-based algorithm for route planning
    """
    try:
        start = data["start"].split(",")
        end = data["end"].split(",")
        min_kw = data["minKw"]
        max_kw = data["maxKw"]
        battery_capacity = float(data['battery'])
        initial_soc = float(data.get('soc', 80))
        
        # Initialize the EV router
        from services.route.dijkstraRouter import EVRouter
        router = EVRouter(
            start=start,
            end=end,
            initial_soc=initial_soc,
            battery_capacity=battery_capacity,
            energy_consumption=ENERGY_CONSUMPTION,
            min_kw=min_kw,
            max_kw=max_kw,
            avg_speed=AVG_SPEED
        )
        
        # Find the optimal route
        result = router.find_optimal_route()
        
        if not result:
            raise Exception("Could not find a viable route with charging stops")
        
        routes = result["routes"]
        soc_values = result["soc_values"]
        charging_stops = result["charging_stops"]
        
        # Calculate total time
        total_time = calculate_total_time(routes, charging_stops, AVG_SPEED)
        
        # Generate map
        map_html = create_map(routes, soc_values, charging_stops, start, end, AVG_SPEED)
        
        return {
            "map_html": map_html,
            "total_time": total_time,
            "charging_stops": charging_stops
        }
        
    except Exception as e:
        print(f"Error in Dijkstra route planning: {str(e)}")
        return {"error": str(e)}, 400

def time_efficient_route(data):
    """
    Find the most time-efficient route balancing driving and charging times
    """
    try:
        start = data["start"].split(",")
        end = data["end"].split(",")
        min_kw = data["minKw"]
        max_kw = data["maxKw"]
        battery_capacity = float(data['battery'])
        initial_soc = float(data.get('soc', 80))
        
        # Get direct route first
        direct_route = get_road_route(start, end)
        soc_values = simulate_soc(direct_route, initial_soc, battery_capacity, ENERGY_CONSUMPTION)
        
        # If we can make it without charging, return the direct route
        if min(soc_values) > 10:  # 10% safety buffer
            map_html = create_map([direct_route], [soc_values], [], start, end, AVG_SPEED)
            total_distance = sum(haversine(direct_route[i], direct_route[i+1]) for i in range(len(direct_route)-1))
            total_time = (total_distance / AVG_SPEED) * 60  # Minutes
            
            return {
                "map_html": map_html,
                "total_time": total_time,
                "charging_stops": []
            }
        
        # Get all potential charging stations along the route
        potential_stations = []
        
        # Sample points along the route at regular intervals
        sample_interval = max(1, len(direct_route) // 10)  # Sample ~10 points along the route
        for i in range(0, len(direct_route), sample_interval):
            point = direct_route[i]
            soc = soc_values[i]
            
            # If SOC is getting low, search for stations
            if soc < 40:  # Start looking when SOC drops below 40%
                stations = get_charging_stations(point[0], point[1], 15, min_kw, max_kw)
                
                for station in stations:
                    # Calculate detour impact
                    detour_to_station = get_road_route(point, station["location"])
                    detour_distance = sum(haversine(detour_to_station[j], detour_to_station[j+1]) 
                                         for j in range(len(detour_to_station)-1))
                    
                    # Calculate energy used and remaining SOC at station
                    energy_used = detour_distance * ENERGY_CONSUMPTION
                    soc_at_station = soc - (energy_used / battery_capacity) * 100
                    
                    # Only consider stations we can reach
                    if soc_at_station > 10:
                        # Calculate time metrics
                        detour_time = (detour_distance / AVG_SPEED) * 60  # Minutes
                        
                        # Calculate route from station to destination
                        route_to_dest = get_road_route(station["location"], end)
                        dest_distance = sum(haversine(route_to_dest[j], route_to_dest[j+1]) 
                                           for j in range(len(route_to_dest)-1))
                        
                        # Add this station to our potential list
                        potential_stations.append({
                            "station": station,
                            "route_index": i,
                            "soc_at_arrival": soc_at_station,
                            "detour_time": detour_time,
                            "distance_to_dest": dest_distance,
                            "point_on_route": point
                        })
        
        # Find optimal combination of charging stops
        best_time = float('inf')
        best_stops = []
        best_routes = []
        best_soc_values = []
        
        # Try various combinations of 0-3 stops
        # For simplicity, we'll just try each station individually first
        for station in potential_stations:
            # Calculate SOC needs
            soc_at_station = station["soc_at_arrival"]
            
            # Calculate route from station to destination
            route_to_dest = get_road_route(station["station"]["location"], end)
            dest_soc_values = simulate_soc(route_to_dest, 80, battery_capacity, ENERGY_CONSUMPTION)
            
            # Check if this single stop is sufficient
            if min(dest_soc_values) > 10:
                # Calculate charging amount and time
                charge_amount = 80 - soc_at_station
                energy_to_add = (charge_amount / 100) * battery_capacity
                charge_time = (energy_to_add / station["station"]["power"]) * 60  # Minutes
                
                # Calculate total route time
                route_to_station = get_road_route(start, station["point_on_route"])
                station_detour = get_road_route(station["point_on_route"], station["station"]["location"])
                
                segment1 = route_to_station + station_detour[1:]  # Avoid duplicate point
                segment1_soc = simulate_soc(segment1, initial_soc, battery_capacity, ENERGY_CONSUMPTION)
                
                total_time = (
                    calculate_total_time([segment1, route_to_dest], 
                                        [{
                                            "station": station["station"],
                                            "charge_time": charge_time,
                                            "charge_amount": charge_amount
                                        }], 
                                        AVG_SPEED)
                )
                
                if total_time < best_time:
                    best_time = total_time
                    best_stops = [{
                        "station": station["station"],
                        "charge_time": charge_time,
                        "charge_amount": charge_amount,
                        "route_index": station["route_index"]
                    }]
                    best_routes = [segment1, route_to_dest]
                    best_soc_values = [segment1_soc, dest_soc_values]
        
        # If we found a good single-stop solution, use it
        if best_stops:
            map_html = create_map(best_routes, best_soc_values, best_stops, start, end, AVG_SPEED)
            return {
                "map_html": map_html,
                "total_time": best_time,
                "charging_stops": best_stops
            }
        
        # If no single stop works, use the multi-stop planning algorithm
        charging_stops = plan_multiple_charging_stops(
            direct_route, initial_soc, battery_capacity, 
            ENERGY_CONSUMPTION, min_kw, max_kw, AVG_SPEED
        )
        
        if not charging_stops:
            raise Exception("Could not find suitable charging stops for this journey")
        
        # Create waypoints and generate route
        waypoints = [start]
        for stop in charging_stops:
            waypoints.append(stop["station"]["location"])
        waypoints.append(end)
        
        # Generate route segments
        routes = []
        soc_values_segments = []
        current_soc = initial_soc
        
        for i in range(len(waypoints) - 1):
            segment = get_road_route(waypoints[i], waypoints[i+1])
            segment_soc = simulate_soc(segment, current_soc, battery_capacity, ENERGY_CONSUMPTION)
            
            routes.append(segment)
            soc_values_segments.append(segment_soc)
            
            # Update SOC after charging
            if i < len(charging_stops):
                current_soc = min(segment_soc[-1] + charging_stops[i]["charge_amount"], 100)
        
        # Calculate total time
        total_time = calculate_total_time(routes, charging_stops, AVG_SPEED)
        
        # Generate map
        map_html = create_map(routes, soc_values_segments, charging_stops, start, end, AVG_SPEED)
        
        return {
            "map_html": map_html,
            "total_time": total_time,
            "charging_stops": charging_stops
        }
        
    except Exception as e:
        print(f"Error in time-efficient route planning: {str(e)}")
        return {"error": str(e)}, 400


if __name__ == '__main__':
    app.run(debug=True)