from typing import Dict, List

import folium

from services.map.socToColor import soc_to_color
from services.route.haversine import haversine


def create_map(routes: List[List[List[float]]], soc_values: List[List[float]], charging_stops: List[Dict], start: List[float], end: List[float], avg_speed: float = 80.0):
    """Create Folium map with route and charging stations"""
    m = folium.Map(location=start, zoom_start=10)
    cumulative_time = 0
    for route, socs in zip(routes, soc_values):
        for i in range(len(route)-1):
            distance = haversine(route[i], route[i+1])
            segment_time = (distance / avg_speed) * 60
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
