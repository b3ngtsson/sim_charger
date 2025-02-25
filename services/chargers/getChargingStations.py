from typing import List, Dict, Optional
import requests
import os
from dotenv import load_dotenv
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

# Load API key from environment
load_dotenv()
API_KEY = os.environ.get('OPENCHARGE_KEY')

# OpenChargeMap API
OCM_URL = "https://api.openchargemap.io/v3/poi/"
OCM_PARAMS = {
    "maxresults": 10,
    "distance": 20,
    "distanceunit": "km",
    "key": API_KEY
}

# Cache results to avoid duplicate API calls
#@lru_cache(maxsize=128)
def get_charging_stations(
    lat: float, 
    lon: float, 
    radius: Optional[int] = 6, 
    min_kw: int = 1, 
    max_kw: int = 150
) -> List[Dict]:
    """
    Fetch charging stations near a coordinate
    
    Args:
        lat: Latitude
        lon: Longitude
        radius: Search radius in km (default: 6)
        min_kw: Minimum charging power in kW
        max_kw: Maximum charging power in kW
        
    Returns:
        List of charging stations with name, location and power
    
    Raises:
        Exception: If API request fails
    """
    if not API_KEY:
        logger.error("OpenChargeMap API key is missing")
        raise ValueError("OpenChargeMap API key is missing. Please set OPENCHARGE_KEY environment variable.")
    
    params = OCM_PARAMS.copy()
    params.update({
        "latitude": lat, 
        "longitude": lon, 
        "distance": radius or 6
    })
    
    logger.info(f"Fetching charging stations near ({lat}, {lon})")
    
    try:
        response = requests.get(OCM_URL, params=params, timeout=3)
        response.raise_for_status()
        
        stations = []
        for station in response.json():
            for conn in station.get("Connections", []):
                if conn.get("PowerKW") is not None and int(min_kw) <= conn["PowerKW"] <= int(max_kw):
                    stations.append({
                        "name": station["AddressInfo"]["Title"],
                        "location": [station["AddressInfo"]["Latitude"], station["AddressInfo"]["Longitude"]],
                        "power": conn["PowerKW"]
                    })
                    break  # Only add station once with first matching connection
        
        logger.info(f"Found {len(stations)} charging stations")
        return stations
    
    except requests.RequestException as e:
        logger.error(f"Error fetching charging stations: {str(e)}")
        raise Exception(f"OpenChargeMap API error: {str(e)}")