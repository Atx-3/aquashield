"""
export_geojson.py - Convert trajectory segments into a GeoJSON file for maps.

GeoJSON is the standard JSON format for map shapes. Each ship segment becomes a
"Feature" with:
    geometry   = LineString (a path) made of [longitude, latitude] pairs
    properties = ship ID, name, type, start/end time, point count
All features are wrapped in one "FeatureCollection".
Input : trajectory_segments.parquet (from build_segments.py)
Output: trajectories/geojson/trajectory_segments.geojson
"""
from pathlib import Path
import json
import duckdb


INPUT_FILE = Path(
    "data/processed/trajectories/trajectory_segments.parquet"
)

OUTPUT_DIR = Path(
    "data/processed/trajectories/geojson"
)

OUTPUT_FILE = OUTPUT_DIR / "trajectory_segments.geojson"


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Trajectory segments file not found: {INPUT_FILE}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    print("=" * 60)
    print("M3 TRAJECTORY → GEOJSON EXPORT")
    print("=" * 60)
    print(f"Input : {INPUT_FILE}")
    print(f"Output: {OUTPUT_FILE}")
    print()

    con = duckdb.connect()

    print("Reading trajectory segments...")

    rows = con.execute(
        f"""
        SELECT
            mmsi,
            segment_number,
            start_time,
            end_time,
            point_count,
            vessel_name,
            vessel_type,
            points
        FROM read_parquet('{INPUT_FILE}')
        ORDER BY mmsi, segment_number
        """
    ).fetchall()

    con.close()

    print(f"Segments loaded: {len(rows):,}")
    print("Building GeoJSON features...")

    features = []

    for row in rows:
        # Unpack the 8 columns of this row into named variables
        (
            mmsi,
            segment_number,
            start_time,
            end_time,
            point_count,
            vessel_name,
            vessel_type,
            points,
        ) = row

        coordinates = []

        for point in points:
            coordinates.append(
                [
                    float(point["longitude"]),
                    float(point["latitude"]),
                ]
            )

        # A LineString needs at least two coordinates.
        if len(coordinates) < 2:
            continue

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates,
            },
            "properties": {
                "mmsi": int(mmsi),
                "segment_number": int(segment_number),
                "start_time": str(start_time),
                "end_time": str(end_time),
                "point_count": int(point_count),
                "vessel_name": (
                    str(vessel_name)
                    if vessel_name is not None
                    else None
                ),
                "vessel_type": (
                    int(vessel_type)
                    if vessel_type is not None
                    else None
                ),
            },
        }

        features.append(feature)

    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    print("Writing GeoJSON...")

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        # separators without spaces = smallest possible file size
        json.dump(
            geojson,
            f,
            separators=(",", ":")
        )

    print()
    print("=" * 60)
    print("GEOJSON EXPORT COMPLETE")
    print("=" * 60)
    print(f"Features written: {len(features):,}")
    print(f"Output file     : {OUTPUT_FILE}")
    print()


if __name__ == "__main__":
    main()
