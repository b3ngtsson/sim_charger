from typing import List, Dict
import requests
import os
from dotenv import load_dotenv


API_KEY = os.environ.get('OPENCHARGE_KEY') 
if API_KEY is None:
    load_dotenv()
    API_KEY = os.getenv('OPENCHARGE_KEY')


# OpenChargeMap API
OCM_URL = "https://api.openchargemap.io/v3/poi/"
OCM_PARAMS = {
    "maxresults": 10,
    "distance": 20,
    "distanceunit": "km",
    "key": API_KEY
}

def get_charging_stations(lat: float, lon: float, radius: int = 6, minKw = 1, maxKw = 150 ) -> List[Dict]:
    """Fetch charging stations near a coordinate"""
    params = OCM_PARAMS.copy()
    params.update({"latitude": lat, "longitude": lon, "distance": radius})
    response = requests.get(OCM_URL, params=params)
    if response.status_code == 200:
        stations = []
        for station in response.json():
            for conn in station["Connections"]:
                if conn["PowerKW"] is not None and int(minKw) <= conn["PowerKW"] <= int(maxKw):
                    stations.append({
                        "name": station["AddressInfo"]["Title"],
                        "location": [station["AddressInfo"]["Latitude"], station["AddressInfo"]["Longitude"]],
                        "power": conn["PowerKW"]
                    })
                    break
        return stations
    else:
        raise Exception("OpenChargeMap API error")
