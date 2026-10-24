"""
find_test_spill.py - Helper script: pick a realistic test "spill" point.

Prints the earliest AIS ping in the cleaned dataset (its time and position). That point
was used as a fake spill location for testing the vessel-search scripts, guaranteeing
at least one ship is nearby.
"""
from pathlib import Path
import duckdb


AIS_FILE = Path("data/processed/ais_clean.parquet")


def main():
    con = duckdb.connect()

    # ORDER BY time + LIMIT 1 = the single earliest row; fetchone() returns it as a tuple
    result = con.execute(
        f"""
        SELECT
            mmsi,
            base_date_time,
            latitude,
            longitude,
            vessel_name
        FROM read_parquet('{AIS_FILE}')
        ORDER BY base_date_time
        LIMIT 1
        """
    ).fetchone()

    con.close()

    print("=" * 60)
    print("TEST SPILL LOCATION")
    print("=" * 60)

    print(f"MMSI      : {result[0]}")
    print(f"Time      : {result[1]}")
    print(f"Latitude  : {result[2]}")
    print(f"Longitude : {result[3]}")
    print(f"Vessel    : {result[4]}")


if __name__ == "__main__":
    main()
