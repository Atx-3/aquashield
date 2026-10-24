"""
find_candidates.py - Command-line script: list UNIQUE ships near a test spill.

Uses DuckDB (an in-process SQL database that can query .parquet files directly) to:
  1. compute each AIS ping's distance to the spill (Haversine formula written in SQL)
     and its time difference from the spill time,
  2. keep pings within RADIUS_KM and ± TIME_WINDOW_MINUTES,
  3. keep only each ship's single closest ping (ROW_NUMBER ... = 1),
  4. print them sorted by distance, then time.
The spill values below are a hard-coded test point (Louisiana, USA, Jan 2025 AIS data).
Run from the M3_handoff folder:  python src/queries/find_candidates.py
"""
from pathlib import Path
import duckdb

AIS_FILE = Path("data/processed/ais_clean.parquet")

SPILL_LAT = 29.86105
SPILL_LON = -90.01582
SPILL_TIME = "2025-01-08 05:30:00"

RADIUS_KM = 10
TIME_WINDOW_MINUTES = 60
LIMIT = 50


def main():
    if not AIS_FILE.exists():
        raise FileNotFoundError(f"AIS file not found: {AIS_FILE}")

    con = duckdb.connect()

    # SQL in 4 stages (each "WITH x AS (...)" is a named temporary result):
    #   calculated     -> add distance_km and time_diff_minutes to each ping in the time window
    #   filtered       -> keep pings inside the radius
    #   ranked         -> per ship (PARTITION BY mmsi): count pings and number them closest-first
    #   unique_vessels -> keep row number 1 = each ship's closest ping
    query = f"""
    WITH calculated AS (
        SELECT
            mmsi,
            base_date_time,
            latitude,
            longitude,
            vessel_name,
            vessel_type,

            6371.0 * 2 * ASIN(
                SQRT(
                    POWER(
                        SIN(RADIANS(latitude - {SPILL_LAT}) / 2),
                        2
                    )
                    +
                    COS(RADIANS({SPILL_LAT}))
                    * COS(RADIANS(latitude))
                    * POWER(
                        SIN(RADIANS(longitude - {SPILL_LON}) / 2),
                        2
                    )
                )
            ) AS distance_km,

            ABS(
                EPOCH(
                    base_date_time
                    - CAST('{SPILL_TIME}' AS TIMESTAMP)
                )
            ) / 60.0 AS time_diff_minutes

        FROM read_parquet('{AIS_FILE}')

        WHERE base_date_time BETWEEN
            CAST('{SPILL_TIME}' AS TIMESTAMP)
            - INTERVAL '{TIME_WINDOW_MINUTES} minutes'
            AND
            CAST('{SPILL_TIME}' AS TIMESTAMP)
            + INTERVAL '{TIME_WINDOW_MINUTES} minutes'
    ),

    filtered AS (
        SELECT *
        FROM calculated
        WHERE distance_km <= {RADIUS_KM}
    ),

    ranked AS (
        SELECT
            *,
            COUNT(*) OVER (
                PARTITION BY mmsi
            ) AS observations_found,

            ROW_NUMBER() OVER (
                PARTITION BY mmsi
                ORDER BY distance_km ASC, time_diff_minutes ASC
            ) AS vessel_row

        FROM filtered
    ),

    unique_vessels AS (
        SELECT
            mmsi,
            vessel_name,
            vessel_type,
            base_date_time AS closest_observation_time,
            latitude AS closest_latitude,
            longitude AS closest_longitude,
            distance_km AS closest_distance_km,
            time_diff_minutes AS closest_time_diff_minutes,
            observations_found
        FROM ranked
        WHERE vessel_row = 1
    )

    SELECT *
    FROM unique_vessels
    ORDER BY
        closest_distance_km ASC,
        closest_time_diff_minutes ASC
    LIMIT {LIMIT}
    """

    # Run the query; fetchall() gives rows as tuples, con.description gives the column names
    results = con.execute(query).fetchall()
    columns = [desc[0] for desc in con.description]

    con.close()

    print("=" * 70)
    print("M3 UNIQUE VESSEL CANDIDATES")
    print("=" * 70)
    print(f"Spill latitude : {SPILL_LAT}")
    print(f"Spill longitude: {SPILL_LON}")
    print(f"Spill time     : {SPILL_TIME}")
    print(f"Radius         : {RADIUS_KM} km")
    print(f"Time window    : ±{TIME_WINDOW_MINUTES} minutes")
    print()

    print(f"Unique vessels returned: {len(results)}")
    print()

    if not results:
        print("No candidate vessels found.")
        return

    for i, row in enumerate(results, 1):
        # Pair column names with values -> {"mmsi": ..., "vessel_name": ..., ...}
        record = dict(zip(columns, row))

        print(
            f"{i:02d}. "
            f"MMSI={record['mmsi']} | "
            f"Name={record['vessel_name']} | "
            f"Type={record['vessel_type']} | "
            f"Distance={record['closest_distance_km']:.3f} km | "
            f"Time diff={record['closest_time_diff_minutes']:.1f} min | "
            f"Observations={record['observations_found']}"
        )

        print(
            f"    Position: "
            f"{record['closest_latitude']}, "
            f"{record['closest_longitude']}"
        )

        print(
            f"    Time: {record['closest_observation_time']}"
        )

    print()
    print("=" * 70)


if __name__ == "__main__":
    main()
