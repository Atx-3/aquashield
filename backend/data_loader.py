"""
AQUA SHIELD: Spatio-Temporal Dataset & Telemetry Store (Gujarat / Arabian Sea Surveillance Sector)

This file holds hand-made demo shapes for the default Gujarat case:
  - a spill outline, a 24h forecast outline, and a 6-hour hindcast path.
Each shape is built as a list of small (lat, lng) offsets added to a base point.
In the current app only get_vessels_dataset() is used (by ais_correlator.py);
the real map shapes come from the upload/drift endpoints instead.
"""
from typing import Dict, List, Any
import math

def get_sar_spill_polygon() -> List[List[float]]:
    """Returns the organic amoeba-like polygon for the detected slick off Gujarat coast."""
    # Centered around lat 21.1520, lng 69.8540
    base_lat = 21.1520
    base_lng = 69.8540
    # Organic slick shape corresponding to the reference image
    offsets = [
        (-0.020, -0.160), (-0.010, -0.120), (0.015, -0.090), (0.025, -0.050),
        (0.010, -0.010), (0.020, 0.040), (0.005, 0.090), (-0.025, 0.130),
        (-0.055, 0.160), (-0.085, 0.180), (-0.110, 0.160), (-0.090, 0.110),
        (-0.060, 0.070), (-0.040, 0.020), (-0.060, -0.030), (-0.080, -0.080),
        (-0.070, -0.130), (-0.045, -0.160)
    ]
    # Add each offset to the base point -> list of [lat, lng] corners (rounded to 5 decimals ≈ 1 m)
    return [[round(base_lat + dlat, 5), round(base_lng + dlng, 5)] for dlat, dlng in offsets]

def get_forecast_polygon_24h() -> List[List[float]]:
    """Returns the forecasted 24h drift dispersion area off Veraval/Somnath coast."""
    base_lat = 21.0500
    base_lng = 70.0200
    offsets = [
        (0.000, 0.120), (0.045, 0.100), (0.085, 0.060), (0.100, 0.015),
        (0.090, -0.040), (0.060, -0.085), (0.015, -0.115), (-0.045, -0.095),
        (-0.090, -0.055), (-0.110, -0.010), (-0.095, 0.060), (-0.040, 0.100)
    ]
    return [[round(base_lat + dlat, 5), round(base_lng + dlng, 5)] for dlat, dlng in offsets]

def get_hindcast_origin_track() -> List[Dict[str, Any]]:
    """Returns the temporal trajectory path from origin (20.8450, 69.5210) to current spill (21.1520, 69.8540)."""
    steps = [
        {"t_offset": "-6h", "time": "04:24 UTC", "lat": 20.8450, "lng": 69.5210, "state": "Probable Origin (Discharge Point)"},
        {"t_offset": "-5h", "time": "05:24 UTC", "lat": 20.8980, "lng": 69.5750, "state": "Initial Advection"},
        {"t_offset": "-4h", "time": "06:24 UTC", "lat": 20.9550, "lng": 69.6380, "state": "Spreading & Weathering"},
        {"t_offset": "-3h", "time": "07:24 UTC", "lat": 21.0150, "lng": 69.7050, "state": "Mid-Track Drift"},
        {"t_offset": "-2h", "time": "08:24 UTC", "lat": 21.0700, "lng": 69.7680, "state": "Current Acceleration"},
        {"t_offset": "-1h", "time": "09:24 UTC", "lat": 21.1150, "lng": 69.8150, "state": "Pre-Detection Position"},
        {"t_offset": "0h", "time": "10:24 UTC", "lat": 21.1520, "lng": 69.8540, "state": "Satellite SAR Detection Point"}
    ]
    return steps

def get_vessels_dataset() -> List[Dict[str, Any]]:
    """Returns historical AIS dataset (empty when no historical dataset matches incident timestamp)."""
    # Always empty: no historical ship database for the Indian coast is bundled with the project.
    return []
