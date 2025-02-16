from typing import List

from services.route.haversine import haversine



def simulate_soc(route: List[List[float]], initial_soc: float, battery_capacity: float, energyConsumption: int = 0) -> List[float]:
    """Calculate SOC at each route point"""
    soc = initial_soc
    soc_values = [soc]
    for i in range(len(route)-1):
        distance = haversine(route[i], route[i+1])
        energy_used = distance * energyConsumption
        soc -= (energy_used / battery_capacity) * 100
        soc = max(soc, 0)
        soc_values.append(soc)
    return soc_values
