from typing import List

from services.route.haversine import haversine



def simulate_soc(route, initial_soc, battery_capacity, energy_consumption):
    """
    Simulate State of Charge (SOC) along a route
    
    Args:
        route: List of [lat, lon] coordinates
        initial_soc: Starting SOC percentage (0-100)
        battery_capacity: Battery capacity in kWh
        energy_consumption: Energy consumption in kWh/km
        
    Returns:
        List of SOC values corresponding to each point in the route
    """
    soc_values = [initial_soc]
    current_soc = initial_soc
    
    for i in range(len(route) - 1):
        # Calculate distance between consecutive points
        distance = haversine(route[i], route[i+1])
        
        # Calculate energy consumed
        energy_used = distance * energy_consumption
        
        # Calculate SOC drop
        soc_drop = (energy_used / battery_capacity) * 100
        
        # Update current SOC
        current_soc -= soc_drop
        current_soc = max(0, current_soc)  # SOC can't go below 0
        
        soc_values.append(current_soc)
    
    return soc_values