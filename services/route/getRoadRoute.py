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
