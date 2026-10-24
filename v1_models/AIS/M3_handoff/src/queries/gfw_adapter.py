"""
Global Fishing Watch (GFW) API Adapter for AQUA SHIELD M3.
Queries GFW API v3 endpoints (presence, vessel search, events) using Authorization: Bearer.
Normalizes real GFW observations into M3 vessel candidate structures.

Global Fishing Watch is a free service with global ship-activity data. This adapter is an
alternative to the Pelyr adapter; it is not called by the current web app.
Flow: ask the "presence" endpoint which vessels were at the spill point on that date
      -> for each, ask the registry endpoint for its name/type/MMSI
      -> keep vessels within radius_km.
"""

import os
import math
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import requests

logger = logging.getLogger("aquashield.gfw")

# ==============================================================================
# CONFIGURATION & API TOKEN PLACEHOLDER
# ==============================================================================
# Paste your real Global Fishing Watch API token below OR set the GFW_API_ACCESS_TOKEN
# environment variable in your shell.
# ==============================================================================
GFW_API_ACCESS_TOKEN = os.getenv("GFW_API_ACCESS_TOKEN", "PASTE_YOUR_GFW_TOKEN_HERE")

GFW_BASE_URL = "https://gateway.api.globalfishingwatch.org/v3"

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two lat/lng points."""
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    return R * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

def is_gfw_token_valid() -> bool:
    """Checks if a non-placeholder token is configured."""
    return bool(
        GFW_API_ACCESS_TOKEN
        and GFW_API_ACCESS_TOKEN != "PASTE_YOUR_GFW_TOKEN_HERE"
        and not GFW_API_ACCESS_TOKEN.startswith("PASTE_")
    )

def query_gfw_vessel_presence(
    spill_lat: float,
    spill_lon: float,
    spill_time: str,
    radius_km: float = 35.0,
    time_window_minutes: int = 60
) -> List[Dict[str, Any]]:
    """
    Queries Global Fishing Watch API v3 for genuine vessel presence / identity observations.
    Converts GFW API responses into normalized M3 vessel candidates.
    If token is invalid, unconfigured, or API returns 401/404, returns [] gracefully.
    """
    if not is_gfw_token_valid():
        logger.info("[GFW Adapter] Token unconfigured or placeholder present. Skipping live GFW API call.")
        return []

    headers = {
        "Authorization": f"Bearer {GFW_API_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    # Parse ISO timestamp (strip a trailing "Z" because older fromisoformat() can't read it)
    try:
        if isinstance(spill_time, str):
            clean_time_str = spill_time.replace("Z", "")
            dt_target = datetime.fromisoformat(clean_time_str).replace(tzinfo=timezone.utc)
        else:
            dt_target = spill_time
    except Exception as e:
        logger.warning(f"[GFW Adapter] Timestamp parse error for '{spill_time}': {e}")
        dt_target = datetime.now(timezone.utc)

    start_date = dt_target.strftime("%Y-%m-%d")
    
    # 1. Query GFW 4Wings Presence Endpoint for vessel presence data
    results = []
    try:
        url_presence = f"{GFW_BASE_URL}/4wings/interaction/vessels"
        params = {
            "datasets[0]": "public-global-presence:latest",
            "start-date": start_date,
            "end-date": start_date,
            "latitude": spill_lat,
            "longitude": spill_lon
        }
        r = requests.get(url_presence, headers=headers, params=params, timeout=10)
        
        if r.status_code == 200:
            data = r.json()
            entries = data.get("entries", []) if isinstance(data, dict) else []
            for entry in entries:
                v_id = entry.get("vesselId") or entry.get("id")
                if not v_id:
                    continue
                
                # Retrieve identity details for returned vessel
                v_info = fetch_gfw_vessel_identity(v_id, headers)
                
                # If GFW gives no position, assume the vessel is at the spill point
                v_lat = float(entry.get("lat") or spill_lat)
                v_lon = float(entry.get("lon") or spill_lon)
                dist = haversine_km(spill_lat, spill_lon, v_lat, v_lon)
                
                if dist <= radius_km:
                    mmsi_val = str(v_info.get("mmsi") or v_id)
                    results.append({
                        "mmsi": mmsi_val,
                        "vessel_name": v_info.get("vessel_name") or f"GFW-VESSEL-{mmsi_val[:8]}",
                        "vessel_type": v_info.get("vessel_type") or "Commercial Vessel (GFW)",
                        "latitude": v_lat,
                        "longitude": v_lon,
                        "timestamp": dt_target.isoformat(),
                        "distance_km": round(dist, 3),
                        "time_difference_minutes": 0.0,
                        "sog": float(entry.get("speed") or 0.0),
                        "cog": float(entry.get("course") or 0.0),
                        "source": "GFW AIS Vessel Presence"
                    })
        else:
            logger.info(f"[GFW Adapter] GFW presence query HTTP {r.status_code}: {r.text[:150]}")
    except Exception as err:
        logger.warning(f"[GFW Adapter] GFW network query exception: {err}")

    return results

def fetch_gfw_vessel_identity(vessel_id: str, headers: Dict[str, str]) -> Dict[str, Any]:
    """Fetches vessel identity from GFW Registry API for a given vessel ID."""
    try:
        url_id = f"{GFW_BASE_URL}/vessels/{vessel_id}"
        r = requests.get(url_id, headers=headers, timeout=5)
        if r.status_code == 200:
            info = r.json()
            return {
                "mmsi": info.get("mmsi") or info.get("ssvid"),
                "vessel_name": info.get("shipname") or info.get("name"),
                "vessel_type": info.get("shiptype") or info.get("vesselType"),
                "flag": info.get("flag")
            }
    except Exception:
        pass
    return {}
