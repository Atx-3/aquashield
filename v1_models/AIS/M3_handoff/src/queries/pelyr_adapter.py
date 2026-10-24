"""
Pelyr HTTPS AIS Data Adapter for AQUA SHIELD M3 Engine.
Queries Pelyr HTTPS API endpoints for historical/live vessel positional tracks using Bearer / API Key authentication.
Normalizes genuine Pelyr AIS records into standard M3 vessel candidate structures.

Pelyr is an online AIS service: ships broadcast their position, speed and identity, and
Pelyr collects them. This file talks to its web API and converts its replies into simple
dictionaries the rest of AQUA SHIELD understands. Three functions:
  query_pelyr_vessels()       - ships in an area on a given date (not used by the web app)
  query_pelyr_live_vessels()  - ships in an area RIGHT NOW (used for steps 5 and 6)
  query_pelyr_vessel_track()  - one ship's recent path (drawn on the map)
All three return empty results (never crash) if no API key is set or the request fails.
"""

import os
import math
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import requests

logger = logging.getLogger("aquashield.pelyr")

# ==============================================================================
# CONFIGURATION & API KEY PLACEHOLDER
# ==============================================================================
# Set your Pelyr API Key in the environment OR paste it into the placeholder below.
# DO NOT COMMIT REAL KEYS TO SOURCE CONTROL.
# ==============================================================================
# Read the key from the environment variable PELYR_API_KEY (empty string if not set).
# NOTE: the app does not load the .env file automatically; set the variable in the
# terminal before starting the server (e.g. PowerShell: $env:PELYR_API_KEY="...").
PELYR_API_KEY = os.getenv("PELYR_API_KEY", "")
PELYR_BASE_URL = os.getenv("PELYR_BASE_URL", "https://api.pelyr.com/v1")

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two lat/lng points (Haversine formula)."""
    R = 6371.0      # Earth radius in km
    # Trig functions need radians, not degrees
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    return R * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

def is_pelyr_key_valid() -> bool:
    """Checks if a valid non-placeholder Pelyr API key is configured."""
    return bool(
        PELYR_API_KEY
        and PELYR_API_KEY != "PASTE_YOUR_PELYR_KEY_HERE"
        and not PELYR_API_KEY.startswith("PASTE_")
    )

def query_pelyr_vessels(
    spill_lat: float,
    spill_lon: float,
    spill_time: str,
    radius_km: float = 35.0,
    time_window_minutes: int = 60
) -> List[Dict[str, Any]]:
    """
    Queries Pelyr HTTPS API for genuine AIS vessel records around target coordinates and time window.
    Returns normalized M3 candidate vessel dictionaries.
    If key is unconfigured or API returns error/empty, returns [] gracefully.
    """
    if not is_pelyr_key_valid():
        logger.info("[Pelyr Adapter] API Key unconfigured or placeholder present. Skipping live Pelyr API call.")
        return []

    # HTTP headers: send the API key both as a Bearer token and as x-api-key
    headers = {
        "Authorization": f"Bearer {PELYR_API_KEY}",
        "x-api-key": PELYR_API_KEY,
        "Content-Type": "application/json"
    }

    # Bounding box calculation around target center (min_lon, min_lat, max_lon, max_lat)
    # 1° latitude ≈ 111 km. 1° longitude is shorter away from the equator (x cos(lat)),
    # so we need MORE degrees of longitude to cover the same km. The API searches this
    # rectangle; we then keep only ships inside the circle using haversine_km().
    lat_delta = radius_km / 111.0
    lon_delta = radius_km / (111.0 * max(math.cos(math.radians(spill_lat)), 0.1))

    min_lat = round(spill_lat - lat_delta, 4)
    max_lat = round(spill_lat + lat_delta, 4)
    min_lon = round(spill_lon - lon_delta, 4)
    max_lon = round(spill_lon + lon_delta, 4)

    bbox_str = f"{min_lon},{min_lat},{max_lon},{max_lat}"

    params = {
        "bbox": bbox_str,
        "start_time": f"{spill_time[:10]}T00:00:00Z",
        "end_time": f"{spill_time[:10]}T23:59:59Z"
    }

    results = []
    try:
        # 1. Query Pelyr AIS Vessels endpoint
        url = f"{PELYR_BASE_URL}/vessels"
        r = requests.get(url, headers=headers, params=params, timeout=12)

        if r.status_code == 200:    # 200 = success
            data = r.json()
            records = data.get("vessels") if isinstance(data, dict) else []

            # Convert each Pelyr record into our standard vessel dictionary
            for item in records:
                if not isinstance(item, dict):
                    continue
                pos = item.get("position") or {}
                st = item.get("static") or {}

                v_lat = float(pos.get("lat") or item.get("latitude") or 0.0)
                v_lon = float(pos.get("lon") or item.get("longitude") or 0.0)
                if v_lat == 0.0 or v_lon == 0.0:
                    continue

                dist = haversine_km(spill_lat, spill_lon, v_lat, v_lon)
                if dist <= radius_km:
                    mmsi_val = str(item.get("mmsi") or "UNKNOWN")
                    results.append({
                        "mmsi": mmsi_val,
                        "vessel_name": str(st.get("name") or f"PELYR-VESSEL-{mmsi_val[:8]}"),
                        "vessel_type": str(st.get("type") or "Commercial Vessel (Pelyr)"),
                        "latitude": v_lat,
                        "longitude": v_lon,
                        "timestamp": str(pos.get("ts") or spill_time),
                        "distance_km": round(dist, 3),
                        "time_difference_minutes": 0.0,
                        "sog": float(pos.get("sog") or 0.0),
                        "cog": float(pos.get("cog") or 0.0),
                        "heading": float(pos.get("heading") or 0.0),
                        "imo": str(st.get("imo") or ""),
                        "source": "Pelyr AIS Data API"
                    })
        else:
            logger.info(f"[Pelyr Adapter] HTTP {r.status_code}: {r.text[:150]}")
    except Exception as err:
        logger.warning(f"[Pelyr Adapter] Network query exception: {err}")

    return results


def query_pelyr_live_vessels(
    center_lat: float,
    center_lng: float,
    radius_km: float = 250.0
) -> Dict[str, Any]:
    """
    Queries Pelyr HTTPS API for REAL live vessel positions around target center coordinates.
    Queries 250 km radius with strict Haversine distance_km <= 250 filtering.
    Does NOT supply historical start_time/end_time parameters.
    Attaches metadata explicitly flagging mode="LIVE", historical=False, attribution_eligible=False.
    """
    # No key -> return an empty "UNCONFIGURED" result (the UI then shows "no vessels")
    if not is_pelyr_key_valid():
        return {"status": "UNCONFIGURED", "http_status": None, "vessels": [], "radius_km": radius_km}

    headers = {
        "Authorization": f"Bearer {PELYR_API_KEY}",
        "x-api-key": PELYR_API_KEY,
        "Content-Type": "application/json"
    }

    # List of search radii to try in order (currently only 250 km; the loop allows adding more)
    radii_to_try = [250.0]
    results = []
    http_status = None
    used_radius = 250.0

    for current_radius in radii_to_try:
        used_radius = current_radius
        lat_delta = current_radius / 111.0
        lon_delta = current_radius / (111.0 * max(math.cos(math.radians(center_lat)), 0.1))

        min_lat = round(center_lat - lat_delta, 4)
        max_lat = round(center_lat + lat_delta, 4)
        min_lon = round(center_lng - lon_delta, 4)
        max_lon = round(center_lng + lon_delta, 4)

        bbox_str = f"{min_lon},{min_lat},{max_lon},{max_lat}"
        params = {"bbox": bbox_str}

        try:
            url = f"{PELYR_BASE_URL}/vessels"
            r = requests.get(url, headers=headers, params=params, timeout=10)
            http_status = r.status_code

            if r.status_code == 200:
                data = r.json()
                # The API may return {"vessels": [...]} or a plain list - handle both
                records = data.get("vessels") if isinstance(data, dict) else (data if isinstance(data, list) else [])

                current_results = []
                for item in records:
                    # Position and static info (name, type, IMO) may be nested or flat
                    if not isinstance(item, dict):
                        continue
                    pos = item.get("position") or {}
                    st = item.get("static") or {}

                    v_lat = float(pos.get("lat") or item.get("latitude") or 0.0)
                    v_lon = float(pos.get("lon") or item.get("longitude") or 0.0)
                    if v_lat == 0.0 or v_lon == 0.0:
                        continue

                    dist = haversine_km(center_lat, center_lng, v_lat, v_lon)
                    if dist <= current_radius:
                        mmsi_val = str(item.get("mmsi") or st.get("mmsi") or "UNKNOWN")
                        current_results.append({
                            "mmsi": mmsi_val,
                            "vessel_name": str(st.get("name") or f"PELYR-LIVE-{mmsi_val[:8]}"),
                            "vessel_type": str(st.get("type") or item.get("vessel_type") or "Commercial Vessel"),
                            "latitude": v_lat,
                            "longitude": v_lon,
                            "timestamp": str(pos.get("ts") or pos.get("timestamp") or item.get("last_seen") or "LIVE"),
                            "distance_km": round(dist, 2),
                            "sog": float(pos.get("sog") or 0.0),
                            "cog": float(pos.get("cog") or 0.0),
                            "heading": float(pos.get("heading") or 0.0),
                            "imo": str(st.get("imo") or ""),
                            "source": "Pelyr",
                            # Flags: this is a current position, so it can't prove who caused a past spill
                            "mode": "LIVE",
                            "historical": False,
                            "attribution_eligible": False
                        })
                
                if current_results:
                    # Sort by distance from M4 origin
                    current_results.sort(key=lambda x: x["distance_km"])
                    results = current_results
                    break
        except Exception as err:
            logger.warning(f"[Pelyr Live Adapter] Query exception at radius {current_radius} km: {err}")

    return {
        "status": "SUCCESS" if http_status == 200 else "ERROR",
        "http_status": http_status,
        "vessels": results,
        "count": len(results),
        "radius_km": used_radius,
        "region_name": "Regional Live AIS Traffic"
    }


# In-memory track cache: (mmsi, from_time, to_time, resolution) -> (timestamp, response_dict)
# Avoids asking the API for the same track again within 5 minutes.
_PELYR_TRACK_CACHE: Dict[str, tuple] = {}
# If the API says "too many requests" (HTTP 429), we wait until this time before asking again
_PELYR_RATE_LIMITED_UNTIL: float = 0.0

def query_pelyr_vessel_track(
    mmsi: str,
    from_time: Optional[str] = None,
    to_time: Optional[str] = None,
    resolution: Optional[str] = "15min"
) -> Dict[str, Any]:
    """
    Queries Pelyr HTTPS API for genuine vessel historical track points:
    GET https://api.pelyr.com/v1/vessels/{mmsi}/track
    Respects rate limits (HTTP 429 Retry-After), caches responses, and falls back to 7d / 1h window if 24h yields 0 points.
    """
    import time
    global _PELYR_RATE_LIMITED_UNTIL

    if not is_pelyr_key_valid() or not mmsi:
        return {
            "status": "UNCONFIGURED",
            "http_status": None,
            "mmsi": mmsi,
            "track_points": [],
            "message": "Pelyr API key is not configured."
        }

    # Still inside a rate-limit wait period -> don't call the API, just report the wait time
    now_time = time.time()
    if now_time < _PELYR_RATE_LIMITED_UNTIL:
        retry_after = int(_PELYR_RATE_LIMITED_UNTIL - now_time) + 1
        return {
            "status": "RATE_LIMITED",
            "http_status": 429,
            "mmsi": mmsi,
            "retry_after": retry_after,
            "track_points": [],
            "message": f"Pelyr historical track temporarily rate-limited. Retry available in {retry_after} seconds."
        }

    now_dt = datetime.now(timezone.utc)
    if not to_time:
        to_time = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Time windows to try: last 24 h in 15-min steps; if that is empty, last 7 days hourly
    windows_to_try = []
    if from_time:
        windows_to_try.append((from_time, to_time, resolution or "15min"))
    else:
        # Default 24-hour window with 15min resolution
        from_24h = (now_dt - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
        windows_to_try.append((from_24h, to_time, "15min"))
        # Fallback 7-day window with 1h resolution
        from_7d = (now_dt - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
        windows_to_try.append((from_7d, to_time, "1h"))

    headers = {
        "Authorization": f"Bearer {PELYR_API_KEY}",
        "x-api-key": PELYR_API_KEY,
        "Content-Type": "application/json"
    }

    url = f"{PELYR_BASE_URL}/vessels/{mmsi}/track"

    for (f_t, t_t, res_opt) in windows_to_try:
        # Return the cached answer if we fetched this exact query less than 5 min ago
        cache_key = f"{mmsi}_{f_t}_{t_t}_{res_opt}"
        if cache_key in _PELYR_TRACK_CACHE:
            cache_ts, cached_res = _PELYR_TRACK_CACHE[cache_key]
            if now_time - cache_ts < 300: # 5 min cache TTL
                return cached_res

        params = {
            "from": f_t,
            "to": t_t,
            "resolution": res_opt
        }

        try:
            r = requests.get(url, headers=headers, params=params, timeout=10)
            http_status = r.status_code

            # 429 = rate limited. The Retry-After header says how many seconds to wait.
            if r.status_code == 429:
                retry_header = r.headers.get("Retry-After", "30")
                try:
                    retry_seconds = int(retry_header)
                except ValueError:
                    retry_seconds = 30
                _PELYR_RATE_LIMITED_UNTIL = time.time() + retry_seconds
                return {
                    "status": "RATE_LIMITED",
                    "http_status": 429,
                    "mmsi": mmsi,
                    "retry_after": retry_seconds,
                    "track_points": [],
                    "message": f"Pelyr historical track temporarily rate-limited. Retry available in {retry_seconds} seconds."
                }

            if r.status_code == 200:
                data = r.json()
                pts = data.get("points") or data.get("track") or (data if isinstance(data, list) else [])
                track_points = []
                for pt in pts:
                    if isinstance(pt, dict):
                        lat = float(pt.get("lat") or pt.get("latitude") or 0.0)
                        lon = float(pt.get("lon") or pt.get("longitude") or 0.0)
                        if lat != 0.0 and lon != 0.0:
                            track_points.append({
                                "lat": lat,
                                "lng": lon,
                                "timestamp": str(pt.get("ts") or pt.get("timestamp") or ""),
                                "sog": float(pt.get("sog") or 0.0),
                                "cog": float(pt.get("cog") or 0.0),
                                "heading": float(pt.get("heading") or 0.0)
                            })

                # Got points -> cache and return; otherwise loop on to the next (wider) window
                if track_points:
                    res_obj = {
                        "status": "SUCCESS",
                        "http_status": 200,
                        "mmsi": mmsi,
                        "track_points": track_points,
                        "count": len(track_points),
                        "from_time": f_t,
                        "to_time": t_t,
                        "resolution": res_opt,
                        "source": "PELYR"
                    }
                    _PELYR_TRACK_CACHE[cache_key] = (now_time, res_obj)
                    return res_obj
        except Exception as err:
            logger.warning(f"[Pelyr Track Adapter] Query exception for MMSI {mmsi}: {err}")
            return {
                "status": "ERROR",
                "http_status": 500,
                "mmsi": mmsi,
                "track_points": [],
                "message": str(err)
            }

    # If all window attempts return 0 points:
    empty_res = {
        "status": "NO_TRACK_DATA",
        "http_status": 200,
        "mmsi": mmsi,
        "track_points": [],
        "count": 0,
        "message": "REAL AIS TRAJECTORY: NO TRACK DATA AVAILABLE FOR THIS TIME WINDOW"
    }
    return empty_res



