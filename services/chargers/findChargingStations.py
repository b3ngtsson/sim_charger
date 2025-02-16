
from typing import Dict, List, Optional

from services.chargers.getChargingStations import get_charging_stations
from services.route.getRoadRoute import get_road_route
from services.route.haversine import haversine


def find_charging_stop(route: List[List[float]], soc_values: List[float], battery_capacity: float, energyConsumption: float, minKw: int, maxKw: int, speed: float) -> Optional[Dict]:
    """Find optimal charging station along the route"""
    for i, (point, soc) in enumerate(zip(route, soc_values)):
        if i % 100 == 0 and soc < 20:
            remaining_distance = sum(haversine(route[j], route[j+1]) for j in range(i, len(route)-1))
            energy_needed = remaining_distance * energyConsumption
            soc_needed = (energy_needed / battery_capacity) * 100

            if soc >= (soc_needed + 10):
                continue

            next_point = route[i+40]
            stations = get_charging_stations(next_point[0], next_point[1], None, minKw, maxKw )
            if not stations:
                continue

            best_station = max(stations, key=lambda x: x["power"])
            detour_route = get_road_route(point, best_station["location"])
            detour_distance = sum(haversine(detour_route[j], detour_route[j+1]) for j in range(len(detour_route)-1))
            detour_time = (detour_distance / speed) * 60

            energy_used_detour = detour_distance * energyConsumption
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