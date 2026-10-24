"""
M3 AIS Intelligence API (stand-alone version, separate from the main web app).

A small FastAPI server that answers questions about ships from a HISTORICAL AIS file
(data/processed/ais_clean.parquet, built by src/cleaning/clean.py):
    /api/ais/vessels/nearby          ships near a point at a given time
    /api/ais/candidates              same ships, scored and ranked as spill suspects
    /api/ais/vessels/{mmsi}          details about one ship
    /api/ais/vessels/{mmsi}/trajectory  that ship's path (GeoJSON)
Run from the M3_handoff folder with:  uvicorn src.api.main:app
NOTE: the data/ folder is not included in this repo, so these endpoints need it generated first.
Polars (pl) is a fast table/DataFrame library, similar to pandas.
"""
from fastapi import FastAPI, Query
from datetime import datetime
import polars as pl
import json

from src.queries.nearby_vessels import find_nearby_vessels
from src.ranking.rank_candidates import rank_candidates

app = FastAPI(
    title="AQUA SHIELD AIS Intelligence API",
    description="AIS vessel detection and trajectory API for AQUA SHIELD",
    version="1.0.0",
)

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
AIS_FILE = BASE_DIR / "data" / "processed" / "ais_clean.parquet"
TRAJECTORY_FILE = BASE_DIR / "data" / "processed" / "trajectories" / "trajectories.geojson"


@app.get("/")
def root():
    return {
        "project": "AQUA SHIELD",
        "module": "M3 - AIS/Data Engineering",
        "status": "online",
        "endpoints": [
            "/api/ais/vessels/nearby",
            "/api/ais/candidates",
            "/api/ais/vessels/{mmsi}",
            "/api/ais/vessels/{mmsi}/trajectory",
        ],
    }


@app.get("/api/ais/vessels/nearby")
def nearby_vessels(
    lat: float,
    lon: float,
    time: str,
    radius_km: float = Query(20, gt=0),
    time_window_minutes: int = Query(30, gt=0),
):
    # Query(20, gt=0) = default 20, and must be greater than 0 (FastAPI validates it)
    # Convert the ISO text time (e.g. "2025-01-08T12:00:00") into a datetime object
    spill_time = datetime.fromisoformat(time)

    # Ships within radius_km of the spill and within ± time_window_minutes of spill_time
    vessels = find_nearby_vessels(
        spill_lat=lat,
        spill_lon=lon,
        spill_time=spill_time,
        radius_km=radius_km,
        time_window_minutes=time_window_minutes,
    )

    return {
        "spill": {
            "latitude": lat,
            "longitude": lon,
            "time": time,
        },
        "radius_km": radius_km,
        "time_window_minutes": time_window_minutes,
        "count": len(vessels),
        "vessels": vessels,
    }


@app.get("/api/ais/candidates")
def candidates(
    lat: float,
    lon: float,
    time: str,
    radius_km: float = Query(20, gt=0),
    time_window_minutes: int = Query(30, gt=0),
):
    spill_time = datetime.fromisoformat(time)

    vessels = find_nearby_vessels(
        spill_lat=lat,
        spill_lon=lon,
        spill_time=spill_time,
        radius_km=radius_km,
        time_window_minutes=time_window_minutes,
    )

    # Score each ship (distance 40%, time 30%, trajectory 20%, type info 10%) and sort
    ranked = rank_candidates(
        vessels,
        radius_km,
        time_window_minutes,
    )

    return {
        "spill": {
            "latitude": lat,
            "longitude": lon,
            "time": time,
        },
        "ranking_method": {
            "distance": "40%",
            "time": "30%",
            "trajectory": "20%",
            "vessel_type": "10%",
        },
        "count": len(ranked),
        "candidates": ranked,
    }


@app.get("/api/ais/vessels/{mmsi}")
def vessel_info(mmsi: int):

    # Load all AIS rows, keep only this ship's rows, oldest first
    df = pl.read_parquet(AIS_FILE)

    vessel = (
        df.filter(pl.col("mmsi") == mmsi)
        .sort("base_date_time")
    )

    if vessel.height == 0:
        return {"error": "Vessel not found"}

    # Static info (name, IMO, size...) is the same in every row, so read it from the first one
    first = vessel.row(0, named=True)

    return {
        "mmsi": mmsi,
        "vessel_name": first["vessel_name"],
        "imo": first["imo"],
        "call_sign": first["call_sign"],
        "vessel_type": first["vessel_type"],
        "length": first["length"],
        "width": first["width"],
        "draft": first["draft"],
        "position_count": vessel.height,
        "first_seen": str(vessel["base_date_time"].min()),
        "last_seen": str(vessel["base_date_time"].max()),
    }


@app.get("/api/ais/vessels/{mmsi}/trajectory")
def vessel_trajectory(mmsi: int):

    # The GeoJSON file (built by src/trajectories/export_geojson.py) holds one "feature"
    # (a line on the map) per ship; return the one whose mmsi matches
    with open(TRAJECTORY_FILE) as f:
        geojson = json.load(f)

    for feature in geojson["features"]:
        if feature["properties"]["mmsi"] == mmsi:
            return feature

    return {
        "error": "Trajectory not found",
        "mmsi": mmsi,
    }
