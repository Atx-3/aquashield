"""
find_nearby_vessels.py - Command-line script: list all AIS pings near a test spill.

Same idea as find_candidates.py but simpler: it returns every matching ping (up to 100),
not just one per ship. Distance uses the Haversine formula written in SQL:
    d = 2R · asin( sqrt( sin²(Δlat/2) + cos(lat1)·cos(lat2)·sin²(Δlon/2) ) ),  R = 6371 km
Run from the M3_handoff folder:  python src/queries/find_nearby_vessels.py
"""
from pathlib import Path
import duckdb


AIS_FILE = Path("data/processed/ais_clean.parquet")

# Example spill location.
# We will replace these with the real M1 spill values later.
SPILL_LAT = 29.86105
SPILL_LON = -90.01582

# Example spill time.
SPILL_TIME = "2025-01-08 05:30:00"

# Search radius in kilometers.
RADIUS_KM = 10

# Search time window in minutes.
TIME_WINDOW_MINUTES = 60


def main():
    if not AIS_FILE.exists():
        raise FileNotFoundError(
            f"Clean AIS file not found: {AIS_FILE}"
        )

    print("=" * 60)
    print("M3 NEARBY VESSEL QUERY")
    print("=" * 60)

    print(f"Spill latitude : {SPILL_LAT}")
    print(f"Spill longitude: {SPILL_LON}")
    print(f"Spill time     : {SPILL_TIME}")
    print(f"Radius         : {RADIUS_KM} km")
    print(f"Time window    : ±{TIME_WINDOW_MINUTES} minutes")
    print()

    con = duckdb.connect()

    query = f"""
        WITH candidates AS (
            SELECT
                mmsi,
                base_date_time,
                longitude,
                latitude,
                vessel_name,
                vessel_type,
                sog,
                cog,

                6371.0 * 2 * ASIN(
                    SQRT(
                        POWER(
                            SIN(
                                RADIANS(latitude - {SPILL_LAT}) / 2
                            ),
                            2
                        )
                        +
                        COS(RADIANS({SPILL_LAT}))
                        * COS(RADIANS(latitude))
                        * POWER(
                            SIN(
                                RADIANS(longitude - {SPILL_LON}) / 2
                            ),
                            2
                        )
                    )
                ) AS distance_km

            FROM read_parquet('{AIS_FILE}')

            WHERE base_date_time BETWEEN
                CAST('{SPILL_TIME}' AS TIMESTAMP)
                    - INTERVAL '{TIME_WINDOW_MINUTES}' MINUTE

                AND

                CAST('{SPILL_TIME}' AS TIMESTAMP)
                    + INTERVAL '{TIME_WINDOW_MINUTES}' MINUTE
        )

        SELECT
            mmsi,
            vessel_name,
            vessel_type,
            base_date_time,
            ROUND(distance_km, 3) AS distance_km,
            sog,
            cog,
            longitude,
            latitude

        FROM candidates

        WHERE distance_km <= {RADIUS_KM}

        ORDER BY
            distance_km ASC,
            ABS(
                EPOCH(
                    base_date_time
                    - CAST('{SPILL_TIME}' AS TIMESTAMP)
                )
            ) ASC

        LIMIT 100
    """

    # fetchdf() returns the result as a pandas DataFrame (a table) for easy printing
    results = con.execute(query).fetchdf()

    con.close()

    print("=" * 60)
    print("RESULTS")
    print("=" * 60)

    if results.empty:
        print("No vessels found.")
        return

    print(f"Vessels found: {len(results)}")
    print()
    print(results.to_string(index=False))


if __name__ == "__main__":
    main()
