from typing import List

import requests

OSRM_URL = "http://router.project-osrm.org/route/v1/driving/{},{};{},{}?overview=full&geometries=geojson"

def get_road_route(start: List[float], end: List[float]) -> List[List[float]]:
    """Fetch road route from OSRM API"""
    url = OSRM_URL.format(start[1], start[0], end[1], end[0])
    response = requests.get(url)
    if response.status_code == 200:
        route = response.json()["routes"][0]["geometry"]["coordinates"]
        return [[lat, lon] for lon, lat in route]
    else:
        raise Exception("OSRM API error")

# Add this to services/route/getRoadRoute.py

def get_road_route_with_waypoints(waypoints):
    """
    Get an optimized road route with multiple waypoints using OSRM
    
    Args:
        waypoints: List of [lat, lon] coordinates including start and end points
        
    Returns:
        Dictionary with route data and waypoint indices
    """
    if len(waypoints) < 2:
        raise ValueError("Need at least 2 waypoints")
        
    # Format coordinates for OSRM (longitude,latitude format)
    coords = [f"{point[1]},{point[0]}" for point in waypoints]
    
    # For many waypoints, we need to break into chunks due to API limitations
    MAX_WAYPOINTS_PER_REQUEST = 25
    
    if len(waypoints) <= MAX_WAYPOINTS_PER_REQUEST:
        # Single request for fewer waypoints
        url = f"http://router.project-osrm.org/route/v1/driving/{';'.join(coords)}?overview=full&geometries=geojson&annotations=true"
        
        response = requests.get(url)
        if response.status_code != 200:
            raise Exception(f"OSRM API error: {response.status_code}")
            
        data = response.json()
        
        # Extract route coordinates and convert from [lon, lat] to [lat, lon]
        geometry = data["routes"][0]["geometry"]["coordinates"]
        route = [[coord[1], coord[0]] for coord in geometry]
        
        # Extract waypoint indices in the route
        waypoint_indices = [leg["steps"][0]["geometry_index"] for leg in data["routes"][0]["legs"]]
        waypoint_indices.insert(0, 0)  # Add start index
        
        return {
            "route": route,
            "waypoint_indices": waypoint_indices,
            "distance": data["routes"][0]["distance"] / 1000,  # Convert to km
            "duration": data["routes"][0]["duration"] / 60     # Convert to minutes
        }
    else:
        # For many waypoints, chain multiple requests
        chunk_size = MAX_WAYPOINTS_PER_REQUEST - 1  # Allow for overlap
        result_route = []
        result_indices = [0]
        total_distance = 0
        total_duration = 0
        
        for i in range(0, len(waypoints) - 1, chunk_size):
            chunk = waypoints[i:i + chunk_size + 1]
            
            if len(chunk) < 2:
                continue
                
            chunk_coords = [f"{point[1]},{point[0]}" for point in chunk]
            url = f"http://router.project-osrm.org/route/v1/driving/{';'.join(chunk_coords)}?overview=full&geometries=geojson&annotations=true"
            
            response = requests.get(url)
            if response.status_code != 200:
                raise Exception(f"OSRM API error on chunk {i}: {response.status_code}")
                
            data = response.json()
            
            # Extract route and convert coordinates
            geometry = data["routes"][0]["geometry"]["coordinates"]
            chunk_route = [[coord[1], coord[0]] for coord in geometry]
            
            # If not the first chunk, remove the duplicate first point
            if i > 0 and result_route:
                chunk_route = chunk_route[1:]
                
            # Get waypoint indices relative to this chunk
            chunk_indices = [leg["steps"][0]["geometry_index"] for leg in data["routes"][0]["legs"]]
            chunk_indices.insert(0, 0)
            
            # Adjust indices to account for previous chunks
            if result_route:
                adjusted_indices = [idx + len(result_route) for idx in chunk_indices[1:]]
                result_indices.extend(adjusted_indices)
            else:
                result_indices.extend(chunk_indices[1:])
                
            # Combine routes
            result_route.extend(chunk_route)
            
            # Add distances and durations
            total_distance += data["routes"][0]["distance"] / 1000
            total_duration += data["routes"][0]["duration"] / 60
        
        return {
            "route": result_route,
            "waypoint_indices": result_indices,
            "distance": total_distance,
            "duration": total_duration
        }