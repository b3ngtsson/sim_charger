from flask import Flask, render_template, request
import os

from services.chargers.findChargingStations import find_charging_stop
from services.map.generateMap import create_map
from services.route.getRoadRoute import get_road_route
from services.soc.simulateSoc import simulate_soc
from services.time.calculateTotalTime import calculate_total_time

app = Flask(__name__, static_url_path='/static')

# Default parameters THAT SHOULD BE CALCULATED
ENERGY_CONSUMPTION = 0.19  # kWh/km
AVG_SPEED = 80  # km/h

#STANDARD VALUES -> set in FE
MIN_KW = 50
MAX_KW = 150

# function so we can insert adress instead. Though, unathorized
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
            soc_values = simulate_soc(direct_route, initial_soc, battery_capacity, ENERGY_CONSUMPTION)
            
            charging_stops = []
            routes = []
            soc_values_full = []
            current_soc = initial_soc
            current_route = direct_route

            while True:
                charging_stop = find_charging_stop(current_route, soc_values, battery_capacity, ENERGY_CONSUMPTION, MIN_KW, MAX_KW, AVG_SPEED)
                if not charging_stop:
                    break
                charging_stops.append(charging_stop)
                
                route_to_charger = current_route[:charging_stop["route_index"] + 1]
                route_to_charger += get_road_route(current_route[charging_stop["route_index"]], charging_stop["station"]["location"])
                route_from_charger = get_road_route(charging_stop["station"]["location"], end)
                
                soc_to_charger = simulate_soc(route_to_charger, current_soc, battery_capacity, ENERGY_CONSUMPTION)
                current_soc = min(soc_to_charger[-1] + charging_stop["charge_amount"], 100)
                soc_from_charger = simulate_soc(route_from_charger, current_soc, battery_capacity, ENERGY_CONSUMPTION)
                
                routes.append(route_to_charger)
                routes.append(route_from_charger)
                soc_values_full.append(soc_to_charger)
                soc_values_full.append(soc_from_charger)
                
                current_route = route_from_charger
                soc_values = soc_from_charger

            if not charging_stops:
                routes = [direct_route]
                soc_values_full = [soc_values]

            total_time = calculate_total_time(routes, charging_stops, AVG_SPEED)
            map_html = create_map(routes, soc_values_full, charging_stops, start, end, AVG_SPEED)
            
            return render_template('results.html', 
                                map_html=map_html,
                                total_time=total_time,
                                charging_stops=charging_stops,
                                start=start,
                                end=end)
        
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
        soc_values = simulate_soc(direct_route, initial_soc, battery_capacity, ENERGY_CONSUMPTION)


        MIN_KW = min_kw
        MAX_KW = max_kw
        charging_stops = []
        routes = []
        soc_values_full = []
        current_soc = initial_soc
        current_route = direct_route

        while True:
            print(f" find charging stop")
            charging_stop = find_charging_stop(current_route, soc_values, battery_capacity, ENERGY_CONSUMPTION, MIN_KW, MAX_KW, AVG_SPEED)
            if not charging_stop:
                break
            charging_stops.append(charging_stop)
            
            route_to_charger = current_route[:charging_stop["route_index"] + 1]
            print(f" get road route")
            route_to_charger += get_road_route(current_route[charging_stop["route_index"]], charging_stop["station"]["location"])
            route_from_charger = get_road_route(charging_stop["station"]["location"], end)
            print(f" simulate soc")

            soc_to_charger = simulate_soc(route_to_charger, current_soc, battery_capacity, ENERGY_CONSUMPTION)
            current_soc = min(soc_to_charger[-1] + charging_stop["charge_amount"], 100)
            print(f" simulate soc")

            soc_from_charger = simulate_soc(route_from_charger, current_soc, battery_capacity, ENERGY_CONSUMPTION)
            
            routes.append(route_to_charger)
            routes.append(route_from_charger)
            soc_values_full.append(soc_to_charger)
            soc_values_full.append(soc_from_charger)
            
            current_route = route_from_charger
            soc_values = soc_from_charger

        if not charging_stops:
            routes = [direct_route]
            soc_values_full = [soc_values]

        total_time = calculate_total_time(routes, charging_stops, AVG_SPEED)
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
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
