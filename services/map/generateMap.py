from typing import Dict, List

import folium

from services.map.socToColor import soc_to_color
from services.route.haversine import haversine

def create_map(routes, soc_values, charging_stops, start, end, avg_speed):
    """
    Create an HTML map visualization of the route with charging stops
    
    Args:
        routes: List of route segments
        soc_values: List of SOC values for each segment
        charging_stops: List of charging stop details
        start: Starting coordinates [lat, lon]
        end: Ending coordinates [lat, lon]
        avg_speed: Average driving speed in km/h
        
    Returns:
        HTML string of map
    """
    # Create a Folium map centered on the start point
    m = folium.Map(location=start, zoom_start=10)
    
    # Add route segments with color coding based on SOC
    for i, (route_segment, segment_soc) in enumerate(zip(routes, soc_values)):
        # Create SOC-based color gradient (green to yellow to red)
        route_with_soc = []
        for j in range(len(route_segment)):
            if j < len(segment_soc):
                soc = segment_soc[j]
                # Color code: green (100% SOC) to red (0% SOC)
                if soc > 50:
                    color = f'#{int(255 - (soc - 50) * 5.1):02x}ff00'  # Green to yellow
                else:
                    color = f'#ff{int(soc * 5.1):02x}00'  # Yellow to red
            else:
                color = '#ff0000'  # Default to red if we don't have SOC data
                
            route_with_soc.append((route_segment[j], color))
        
        # Add colored route segments
        for j in range(len(route_with_soc) - 1):
            point1, color1 = route_with_soc[j]
            point2, color2 = route_with_soc[j + 1]
            
            # Use average color for the line segment
            folium.PolyLine(
                [point1, point2],
                color=color1,
                weight=4,
                opacity=0.8
            ).add_to(m)
    
    # Add charging stops as markers
    for i, stop in enumerate(charging_stops):
        location = stop["station"]["location"]
        charge_time = stop["charge_time"]
        charge_amount = stop["charge_amount"]
        power = stop["station"]["power"]
        
        # Create popup content
        popup_html = f"""
        <div style="width: 200px">
            <h4>Charging Stop #{i+1}</h4>
            <p><b>Power:</b> {power} kW</p>
            <p><b>Charge time:</b> {int(charge_time)} minutes</p>
            <p><b>Charge amount:</b> {int(charge_amount)}%</p>
        </div>
        """
        
        # Add marker with popup
        folium.Marker(
            location=location,
            popup=folium.Popup(popup_html, max_width=300),
            icon=folium.Icon(color='blue', icon='plug', prefix='fa')
        ).add_to(m)
    
    # Add start and end markers
    folium.Marker(
        location=start,
        popup='Start',
        icon=folium.Icon(color='green', icon='play', prefix='fa')
    ).add_to(m)
    
    folium.Marker(
        location=end,
        popup='Destination',
        icon=folium.Icon(color='red', icon='flag-checkered', prefix='fa')
    ).add_to(m)
    
    # Add a legend
    legend_html = """
    <div style="position: fixed; bottom: 50px; left: 50px; z-index: 1000; background-color: white; padding: 10px; border-radius: 5px; border: 1px solid grey">
        <h4>Battery State</h4>
        <div style="display: flex; align-items: center; margin-bottom: 5px;">
            <div style="width: 20px; height: 10px; background-color: #00ff00; margin-right: 5px;"></div>
            <span>100% SOC</span>
        </div>
        <div style="display: flex; align-items: center; margin-bottom: 5px;">
            <div style="width: 20px; height: 10px; background-color: #ffff00; margin-right: 5px;"></div>
            <span>50% SOC</span>
        </div>
        <div style="display: flex; align-items: center;">
            <div style="width: 20px; height: 10px; background-color: #ff0000; margin-right: 5px;"></div>
            <span>0% SOC</span>
        </div>
    </div>
    """
    
    # Add the legend to the map
    m.get_root().html.add_child(folium.Element(legend_html))
    
    # Fit map to bounds
    all_points = [point for route in routes for point in route]
    m.fit_bounds([
        [min(p[0] for p in all_points), min(p[1] for p in all_points)],
        [max(p[0] for p in all_points), max(p[1] for p in all_points)]
    ])
    
    # Return the map as HTML
    return m._repr_html_()