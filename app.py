from flask import Flask, render_template, request
import folium
import requests
import math
import matplotlib.colors as mcolors
from typing import List, Dict, Optional
import os
app = Flask(__name__)

# OSRM API endpoint
OSRM_URL = "http://router.project-osrm.org/route/v1/driving/{},{};{},{}?overview=full&geometries=geojson"
API_KEY = os.environ.get('OPENCHARGE_KEY')  

# OpenChargeMap API
OCM_URL = "https://api.openchargemap.io/v3/poi/"
OCM_PARAMS = {
    "maxresults": 10,
    "distance": 20,
    "distanceunit": "km",
    "key": API_KEY
}

# Default parameters
ENERGY_CONSUMPTION = 0.19  # kWh/km
AVG_SPEED = 80  # km/h

MIN_KW = 50
MAX_KW = 150

#def geocode_address(address: str) -> List[float]:
#    """Convert address to coordinates using Nominatim"""
#    url = "https://nominatim.openstreetmap.org/search"
#    params = {'q': address, 'format': 'json', 'limit': 1}
#    response = requests.get(url, params=params)
#    print(f"response: {response}")
#    if response.status_code == 200 and response.json():
#        data = response.json()[0]
#        return [float(data['lat']), float(data['lon'])]
#    raise ValueError("Could not geocode address")
#
def get_road_route(start: List[float], end: List[float]) -> List[List[float]]:
    """Fetch road route from OSRM API"""
    url = OSRM_URL.format(start[1], start[0], end[1], end[0])
    response = requests.get(url)
    if response.status_code == 200:
        route = response.json()["routes"][0]["geometry"]["coordinates"]
        return [[lat, lon] for lon, lat in route]
    else:
        raise Exception("OSRM API error")

def haversine(coord1: List[float], coord2: List[float]) -> float:
    """Calculate distance between two coordinates (in km)"""
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def soc_to_color(soc: float) -> str:
    """Map SOC to a gradient color (green → red)"""
    cmap = mcolors.LinearSegmentedColormap.from_list("soc", ["green", "yellow", "red"])
    return mcolors.to_hex(cmap(1 - soc/100))

def get_charging_stations(lat: float, lon: float, radius: int = 6) -> List[Dict]:
    """Fetch charging stations near a coordinate"""
    params = OCM_PARAMS.copy()
    params.update({"latitude": lat, "longitude": lon, "distance": radius})
    response = requests.get(OCM_URL, params=params)
    if response.status_code == 200:
        stations = []
        for station in response.json():
            for conn in station["Connections"]:
                if conn["PowerKW"] is not None and MIN_KW <= conn["PowerKW"] <= MAX_KW:
                    stations.append({
                        "name": station["AddressInfo"]["Title"],
                        "location": [station["AddressInfo"]["Latitude"], station["AddressInfo"]["Longitude"]],
                        "power": conn["PowerKW"]
                    })
                    break
        return stations
    else:
        raise Exception("OpenChargeMap API error")

def simulate_soc(route: List[List[float]], initial_soc: float, battery_capacity: float) -> List[float]:
    """Calculate SOC at each route point"""
    soc = initial_soc
    soc_values = [soc]
    for i in range(len(route)-1):
        distance = haversine(route[i], route[i+1])
        energy_used = distance * ENERGY_CONSUMPTION
        soc -= (energy_used / battery_capacity) * 100
        soc = max(soc, 0)
        soc_values.append(soc)
    return soc_values

def find_charging_stop(route: List[List[float]], soc_values: List[float], battery_capacity: float) -> Optional[Dict]:
    """Find optimal charging station along the route"""
    for i, (point, soc) in enumerate(zip(route, soc_values)):
        if i % 100 == 0 and soc < 30:
            remaining_distance = sum(haversine(route[j], route[j+1]) for j in range(i, len(route)-1))
            energy_needed = remaining_distance * ENERGY_CONSUMPTION
            soc_needed = (energy_needed / battery_capacity) * 100

            if soc >= (soc_needed + 10):
                continue

            next_point = route[i+40]
            stations = get_charging_stations(next_point[0], next_point[1])
            if not stations:
                continue

            best_station = max(stations, key=lambda x: x["power"])
            detour_route = get_road_route(point, best_station["location"])
            detour_distance = sum(haversine(detour_route[j], detour_route[j+1]) for j in range(len(detour_route)-1))
            detour_time = (detour_distance / AVG_SPEED) * 60

            energy_used_detour = detour_distance * ENERGY_CONSUMPTION
            soc_after_detour = soc - (energy_used_detour / battery_capacity) * 100
            soc_after_detour = max(soc_after_detour, 0)

            required_soc = soc_needed + 10
            charge_amount = max(required_soc - soc_after_detour, 10)
            charge_amount = min(charge_amount, 100 - soc_after_detour)

            energy_needed = (charge_amount / 100) * battery_capacity
            charge_time = (energy_needed / best_station["power"]) * 60

            return {
                "station": best_station,
                "charge_time": charge_time,
                "detour_time": detour_time,
                "route_index": i,
                "charge_amount": charge_amount
            }
    return None

def calculate_total_time(routes: List[List[List[float]]], charging_stops: List[Dict]) -> float:
    """Calculate total travel time (driving + charging)"""
    total_time = 0
    for route in routes:
        distance = sum(haversine(route[i], route[i+1]) for i in range(len(route)-1))
        total_time += (distance / AVG_SPEED) * 60
    for stop in charging_stops:
        total_time += stop["charge_time"]
    return total_time

def create_map(routes: List[List[List[float]]], soc_values: List[List[float]], charging_stops: List[Dict], start: List[float], end: List[float]):
    """Create Folium map with route and charging stations"""
    m = folium.Map(location=start, zoom_start=10)
    cumulative_time = 0
    for route, socs in zip(routes, soc_values):
        for i in range(len(route)-1):
            distance = haversine(route[i], route[i+1])
            segment_time = (distance / AVG_SPEED) * 60
            cumulative_time += segment_time
            tooltip = f"SOC: {socs[i]:.1f}% | Time: {cumulative_time:.1f} min"
            folium.PolyLine(
                locations=[route[i], route[i+1]],
                color=soc_to_color(socs[i]),
                weight=5,
                opacity=0.7,
                tooltip=tooltip
            ).add_to(m)
    
    for stop in charging_stops:
        station = stop["station"]
        folium.Marker(
            location=station["location"],
            popup=f"{station['name']} ({station['power']} kW)",
            icon=folium.Icon(color="orange", icon="bolt")
        ).add_to(m)
    
    folium.Marker(start, popup="Start", icon=folium.Icon(color="green")).add_to(m)
    folium.Marker(end, popup="End", icon=folium.Icon(color="red")).add_to(m)
    return m._repr_html_()

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        start = request.form["start"].split(",")
        end = request.form["end"].split(",")
        min_kw = request.form["minKw"]
        max_kw = request.form["maxKw"]
        battery_capacity = float(request.form['battery'])
        initial_soc = float(request.form.get('soc', 80))

        try:
            MIN_KW = min_kw
            MAX_KW = max_kw

            direct_route = get_road_route(start, end)
            soc_values = simulate_soc(direct_route, initial_soc, battery_capacity)
            
            charging_stops = []
            routes = []
            soc_values_full = []
            current_soc = initial_soc
            current_route = direct_route

            while True:
                charging_stop = find_charging_stop(current_route, soc_values, battery_capacity)
                if not charging_stop:
                    break
                charging_stops.append(charging_stop)
                
                route_to_charger = current_route[:charging_stop["route_index"] + 1]
                route_to_charger += get_road_route(current_route[charging_stop["route_index"]], charging_stop["station"]["location"])
                route_from_charger = get_road_route(charging_stop["station"]["location"], end)
                
                soc_to_charger = simulate_soc(route_to_charger, current_soc, battery_capacity)
                current_soc = min(soc_to_charger[-1] + charging_stop["charge_amount"], 100)
                soc_from_charger = simulate_soc(route_from_charger, current_soc, battery_capacity)
                
                routes.append(route_to_charger)
                routes.append(route_from_charger)
                soc_values_full.append(soc_to_charger)
                soc_values_full.append(soc_from_charger)
                
                current_route = route_from_charger
                soc_values = soc_from_charger

            if not charging_stops:
                routes = [direct_route]
                soc_values_full = [soc_values]

            total_time = calculate_total_time(routes, charging_stops)
            map_html = create_map(routes, soc_values_full, charging_stops, start, end)
            
            return render_template('results.html', 
                                map_html=map_html,
                                total_time=total_time,
                                charging_stops=charging_stops,
                                start=start_address,
                                end=end_address)
        
        except Exception as e:
            return render_template('index.html', error=str(e))
    
    return render_template('index.html')

@app.route('/calculate', methods=['POST'])
def calculate_route():
    print(f"calculate")
    data = request.get_json()
    print(f"data {data}")

    try:
        start = data["start"].split(",") #request.form["start"].split(",")
        end =  data["end"].split(",")
        min_kw = data["minKw"]
        max_kw = data["maxKw"]
        battery_capacity = float(data['battery'])
        initial_soc = float(data.get('soc', 80))
        print(f"get route")
        direct_route = get_road_route(start, end)
        print(f"simulate soc")
        soc_values = simulate_soc(direct_route, initial_soc, battery_capacity)
        print(f" after simulate soc")

        MIN_KW = min_kw
        MAX_KW = max_kw
        charging_stops = []
        routes = []
        soc_values_full = []
        current_soc = initial_soc
        current_route = direct_route

        while True:
            charging_stop = find_charging_stop(current_route, soc_values, battery_capacity)
            if not charging_stop:
                break
            charging_stops.append(charging_stop)
            
            route_to_charger = current_route[:charging_stop["route_index"] + 1]
            route_to_charger += get_road_route(current_route[charging_stop["route_index"]], charging_stop["station"]["location"])
            route_from_charger = get_road_route(charging_stop["station"]["location"], end)
            
            soc_to_charger = simulate_soc(route_to_charger, current_soc, battery_capacity)
            current_soc = min(soc_to_charger[-1] + charging_stop["charge_amount"], 100)
            soc_from_charger = simulate_soc(route_from_charger, current_soc, battery_capacity)
            
            routes.append(route_to_charger)
            routes.append(route_from_charger)
            soc_values_full.append(soc_to_charger)
            soc_values_full.append(soc_from_charger)
            
            current_route = route_from_charger
            soc_values = soc_from_charger

        if not charging_stops:
            routes = [direct_route]
            soc_values_full = [soc_values]

        total_time = calculate_total_time(routes, charging_stops)
        map_html = create_map(routes, soc_values_full, charging_stops, start, end)
        print(f"returning now")
        
        return {
            "map_html": map_html,
            "total_time": total_time,
            "charging_stops": charging_stops
        }
    
    except Exception as e:
        print(f"error: {str(e)}")
        return {"error": str(e)}, 400
    
if __name__ == '__main__':
    app.run(debug=True)
