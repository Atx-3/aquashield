"""
build_trajectories.py - One full trajectory (list of points) per ship.

Simpler than build_segments.py: groups ALL of a ship's pings into a single time-ordered
list, without splitting at gaps.
  GROUP BY mmsi                     -> one row per ship
  list(struct_pack(...) ORDER BY t) -> collect its (lon, lat, time) points in time order
Output: data/processed/trajectories/trajectory_points.parquet
"""
from pathlib import Path

import duckdb


INPUT_FILE = Path("data/processed/ais_clean.parquet")
OUTPUT_DIR = Path("data/processed/trajectories")
OUTPUT_FILE = OUTPUT_DIR / "trajectory_points.parquet"


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Clean AIS file not found: {INPUT_FILE}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    print("=" * 60)
    print("M3 AIS TRAJECTORY BUILDER")
    print("=" * 60)
    print(f"Input : {INPUT_FILE}")
    print(f"Output: {OUTPUT_FILE}")
    print()

    con = duckdb.connect()

    print("Building vessel trajectories...")

    query = f"""
        COPY (
            SELECT
                mmsi,
                MIN(base_date_time) AS start_time,
                MAX(base_date_time) AS end_time,
                ANY_VALUE(vessel_name) AS vessel_name,
                ANY_VALUE(vessel_type) AS vessel_type,

                list(
                    struct_pack(
                        longitude,
                        latitude,
                        base_date_time
                    )
                    ORDER BY base_date_time
                ) AS points

            FROM read_parquet('{INPUT_FILE}')

            WHERE longitude IS NOT NULL
              AND latitude IS NOT NULL
              AND base_date_time IS NOT NULL

            GROUP BY mmsi
            ORDER BY mmsi
        )
        TO '{OUTPUT_FILE}'
        (FORMAT PARQUET, COMPRESSION ZSTD);
    """

    con.execute(query)

    # Verify the result before finishing.
    result = con.execute(
        f"""
        SELECT
            COUNT(*) AS vessels,
            SUM(array_length(points)) AS trajectory_points,
            MIN(start_time) AS earliest_start,
            MAX(end_time) AS latest_end
        FROM read_parquet('{OUTPUT_FILE}')
        """
    ).fetchone()

    con.close()

    print()
    print("=" * 60)
    print("TRAJECTORY BUILD COMPLETE")
    print("=" * 60)
    print(f"Vessels          : {result[0]:,}")
    print(f"Trajectory points: {result[1]:,}")
    print(f"Earliest start   : {result[2]}")
    print(f"Latest end       : {result[3]}")
    print()
    print(f"Output file      : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
