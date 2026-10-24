"""
nearby_vessels.py - Find ships near a spill at a given time (used by src/api/main.py).

Two-stage search for speed:
  1. Cheap filter with Polars: keep rows inside the time window AND inside a lat/lng
     rectangle around the spill (no trigonometry needed).
  2. Exact filter in Python: compute the true Haversine distance for the remaining rows
     and keep those within radius_km.
Finally keep only each ship's closest position.
"""
from pathlib import Path
import polars as pl
from math import radians, sin, cos, sqrt, atan2

BASE_DIR = Path(__file__).resolve().parent.parent.parent
INPUT = BASE_DIR / "data" / "processed" / "ais_clean.parquet"


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km between two lat/lng points."""
    R = 6371.0

    lat1 = radians(lat1)
    lat2 = radians(lat2)
    dlat = lat2 - lat1
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def find_nearby_vessels(
    spill_lat,
    spill_lon,
    spill_time,
    radius_km=20,
    time_window_minutes=30,
):
    df = pl.read_parquet(INPUT)

    # Convert input time to Python datetime
    from datetime import datetime, timezone

    if isinstance(spill_time, str):
        spill_time = datetime.fromisoformat(spill_time)

    # Make timezone-aware (UTC) to match base_date_time column in parquet
    if spill_time.tzinfo is None:
        spill_time = spill_time.replace(tzinfo=timezone.utc)

    # First filter by time and rough geographic bounding box
    # (1° latitude ≈ 111 km; longitude degrees shrink by cos(latitude))
    lat_delta = radius_km / 111.0
    lon_delta = radius_km / (111.0 * max(cos(radians(spill_lat)), 0.1))

    candidates = df.filter(
        (pl.col("base_date_time") >= spill_time.replace(
            second=0, microsecond=0
        ) - __import__("datetime").timedelta(minutes=time_window_minutes))
        &
        (pl.col("base_date_time") <= spill_time.replace(
            second=0, microsecond=0
        ) + __import__("datetime").timedelta(minutes=time_window_minutes))
        &
        (pl.col("latitude") >= spill_lat - lat_delta)
        &
        (pl.col("latitude") <= spill_lat + lat_delta)
        &
        (pl.col("longitude") >= spill_lon - lon_delta)
        &
        (pl.col("longitude") <= spill_lon + lon_delta)
    )

    results = []

    for row in candidates.iter_rows(named=True):
        if row["latitude"] is None or row["longitude"] is None:
            continue

        distance = haversine_km(
            spill_lat,
            spill_lon,
            row["latitude"],
            row["longitude"],
        )

        if distance <= radius_km:
            # How many minutes this ping is from the spill time (always positive)
            time_diff = abs(
                (row["base_date_time"] - spill_time).total_seconds()
            ) / 60

            results.append({
                "mmsi": row["mmsi"],
                "vessel_name": row["vessel_name"],
                "vessel_type": row["vessel_type"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "timestamp": str(row["base_date_time"]),
                "distance_km": round(distance, 3),
                "time_difference_minutes": round(time_diff, 2),
                "sog": row["sog"],
                "cog": row["cog"],
            })

    # Keep closest position for each vessel
    unique = {}

    for item in results:
        mmsi = item["mmsi"]

        if mmsi not in unique or item["distance_km"] < unique[mmsi]["distance_km"]:
            unique[mmsi] = item

    return list(unique.values())


if __name__ == "__main__":
    # Quick manual test: ships near Seattle on 8 Jan 2025 at 12:00
    from datetime import datetime

    results = find_nearby_vessels(
        spill_lat=47.68,
        spill_lon=-122.40,
        spill_time=datetime(2025, 1, 8, 12, 0),
        radius_km=20,
        time_window_minutes=30,
    )

    print(f"\nFound {len(results)} nearby vessels\n")

    for vessel in sorted(results, key=lambda x: x["distance_km"])[:20]:
        print(
            f"{vessel['mmsi']} | "
            f"{vessel['vessel_name']} | "
            f"{vessel['distance_km']} km | "
            f"{vessel['timestamp']}"
        )
