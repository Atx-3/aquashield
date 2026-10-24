"""
build_segments.py - Split each ship's AIS pings into continuous trip "segments".

If a ship goes silent for more than 30 minutes, the next ping starts a new segment
(so we never draw a straight line across a long gap). SQL steps:
  ordered  - LAG() gets each ping's previous timestamp for the same ship
  marked   - new_segment = 1 if it's the first ping or the gap > MAX_GAP_MINUTES
  numbered - running SUM of new_segment = segment number (1, 1, 1, 2, 2, 3 ...)
  final    - one row per (ship, segment) with start/end time and the list of points
Output: data/processed/trajectories/trajectory_segments.parquet
"""
from pathlib import Path

import duckdb


INPUT_FILE = Path("data/processed/ais_clean.parquet")
OUTPUT_DIR = Path("data/processed/trajectories")
OUTPUT_FILE = OUTPUT_DIR / "trajectory_segments.parquet"

# If a vessel has no AIS message for more than this amount of time,
# start a new trajectory segment.
MAX_GAP_MINUTES = 30


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
    print("M3 AIS TRAJECTORY SEGMENT BUILDER")
    print("=" * 60)
    print(f"Input : {INPUT_FILE}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Gap threshold: {MAX_GAP_MINUTES} minutes")
    print()

    con = duckdb.connect()

    print("Detecting trajectory gaps and building segments...")

    query = f"""
        COPY (
            WITH ordered AS (
                SELECT
                    mmsi,
                    base_date_time,
                    longitude,
                    latitude,
                    vessel_name,
                    vessel_type,
                    sog,
                    cog,

                    LAG(base_date_time) OVER (
                        PARTITION BY mmsi
                        ORDER BY base_date_time
                    ) AS previous_time

                FROM read_parquet('{INPUT_FILE}')

                WHERE longitude IS NOT NULL
                  AND latitude IS NOT NULL
                  AND base_date_time IS NOT NULL
            ),

            marked AS (
                SELECT
                    *,
                    CASE
                        WHEN previous_time IS NULL THEN 1

                        WHEN date_diff(
                            'minute',
                            previous_time,
                            base_date_time
                        ) > {MAX_GAP_MINUTES}
                        THEN 1

                        ELSE 0
                    END AS new_segment
                FROM ordered
            ),

            numbered AS (
                SELECT
                    *,
                    SUM(new_segment) OVER (
                        PARTITION BY mmsi
                        ORDER BY base_date_time
                        ROWS BETWEEN UNBOUNDED PRECEDING
                        AND CURRENT ROW
                    ) AS segment_number
                FROM marked
            )

            SELECT
                mmsi,
                segment_number,
                MIN(base_date_time) AS start_time,
                MAX(base_date_time) AS end_time,
                COUNT(*) AS point_count,
                ANY_VALUE(vessel_name) AS vessel_name,
                ANY_VALUE(vessel_type) AS vessel_type,

                list(
                    struct_pack(
                        longitude,
                        latitude,
                        base_date_time,
                        sog,
                        cog
                    )
                    ORDER BY base_date_time
                ) AS points

            FROM numbered

            GROUP BY
                mmsi,
                segment_number

            ORDER BY
                mmsi,
                segment_number
        )
        TO '{OUTPUT_FILE}'
        (FORMAT PARQUET, COMPRESSION ZSTD);
    """

    con.execute(query)

    # Read back summary statistics to verify the output file
    result = con.execute(
        f"""
        SELECT
            COUNT(*) AS segments,
            COUNT(DISTINCT mmsi) AS vessels,
            SUM(point_count) AS points,
            MIN(start_time) AS earliest_start,
            MAX(end_time) AS latest_end,
            AVG(point_count) AS avg_points_per_segment
        FROM read_parquet('{OUTPUT_FILE}')
        """
    ).fetchone()

    con.close()

    print()
    print("=" * 60)
    print("TRAJECTORY SEGMENT BUILD COMPLETE")
    print("=" * 60)
    print(f"Vessels              : {result[1]:,}")
    print(f"Trajectory segments   : {result[0]:,}")
    print(f"Trajectory points     : {result[2]:,}")
    print(f"Average points/segment: {result[5]:.1f}")
    print(f"Earliest start        : {result[3]}")
    print(f"Latest end            : {result[4]}")
    print()
    print(f"Output file           : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
