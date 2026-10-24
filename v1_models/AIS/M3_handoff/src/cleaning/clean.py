"""
clean.py - AIS data cleaning pipeline (first step of the M3 data workflow).

Input : one day of raw US AIS broadcasts (a large compressed CSV, ais-2025-01-08.csv.zst)
Output: data/processed/ais_clean.parquet - validated, de-duplicated, sorted by ship & time

Why chunks? The raw file is too big to load into memory at once, so pandas reads it
250,000 rows at a time; each cleaned chunk is saved as a small parquet "part" file,
and DuckDB then merges all parts, removes duplicates and sorts - without loading
everything into memory.

Parquet = compressed, column-based file format, much faster to query than CSV.
"""
import shutil
from pathlib import Path

import duckdb
import pandas as pd


INPUT_FILE = Path("data/raw/ais/ais-2025-01-08.csv.zst")
OUTPUT_FILE = Path("data/processed/ais_clean.parquet")
TEMP_DIR = Path("data/processed/ais_parts")

CHUNK_SIZE = 250_000


def validate_input():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"AIS input file not found: {INPUT_FILE}"
        )


def clean_chunk(df: pd.DataFrame) -> pd.DataFrame:
    # Pattern used throughout: pd.to_numeric(..., errors="coerce") turns unreadable values
    # into NaN (missing) instead of crashing; then out-of-range values are dropped or
    # set to missing (pd.NA).
    # -----------------------------
    # Timestamp
    # -----------------------------
    df["base_date_time"] = pd.to_datetime(
        df["base_date_time"],
        errors="coerce",
        utc=True
    )

    # -----------------------------
    # MMSI
    # -----------------------------
    df["mmsi"] = pd.to_numeric(
        df["mmsi"],
        errors="coerce"
    )

    # A valid MMSI (ship radio ID) has exactly 9 digits; drop rows without one
    df = df[
        df["mmsi"].notna()
        & df["mmsi"].between(100_000_000, 999_999_999)
    ]

    df["mmsi"] = df["mmsi"].astype("int64")

    # -----------------------------
    # Coordinates
    # -----------------------------
    df["longitude"] = pd.to_numeric(
        df["longitude"],
        errors="coerce"
    )

    df["latitude"] = pd.to_numeric(
        df["latitude"],
        errors="coerce"
    )

    # Drop rows with impossible positions (outside the valid range on Earth)
    df = df[
        df["longitude"].between(-180, 180)
        & df["latitude"].between(-90, 90)
    ]

    # -----------------------------
    # Speed Over Ground
    # AIS SOG maximum is 102.2 knots.
    # -----------------------------
    df["sog"] = pd.to_numeric(
        df["sog"],
        errors="coerce"
    )

    df.loc[
        ~df["sog"].between(0, 102.2),
        "sog"
    ] = pd.NA

    # -----------------------------
    # Course Over Ground
    # -----------------------------
    df["cog"] = pd.to_numeric(
        df["cog"],
        errors="coerce"
    )

    df.loc[
        ~df["cog"].between(0, 360),
        "cog"
    ] = pd.NA

    # -----------------------------
    # Heading
    # 511 is the AIS "not available"
    # value, so convert it to missing.
    # -----------------------------
    df["heading"] = pd.to_numeric(
        df["heading"],
        errors="coerce"
    )

    df.loc[df["heading"] == 511, "heading"] = pd.NA

    df.loc[
        ~df["heading"].between(0, 359),
        "heading"
    ] = pd.NA

    # -----------------------------
    # Vessel type
    # -----------------------------
    df["vessel_type"] = pd.to_numeric(
        df["vessel_type"],
        errors="coerce"
    )

    df.loc[
        ~df["vessel_type"].between(0, 99),
        "vessel_type"
    ] = pd.NA

    # -----------------------------
    # Navigation status
    # -----------------------------
    df["status"] = pd.to_numeric(
        df["status"],
        errors="coerce"
    )

    df.loc[
        ~df["status"].between(0, 15),
        "status"
    ] = pd.NA

    # -----------------------------
    # Dimensions
    # -----------------------------
    for column in ["length", "width", "draft"]:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

        df.loc[
            df[column] < 0,
            column
        ] = pd.NA

    # -----------------------------
    # Cargo
    # -----------------------------
    df["cargo"] = pd.to_numeric(
        df["cargo"],
        errors="coerce"
    )

    # -----------------------------
    # Text fields
    # -----------------------------
    text_columns = [
        "vessel_name",
        "imo",
        "call_sign",
        "transceiver",
    ]

    for column in text_columns:
        df[column] = (
            df[column]
            .astype("string")
            .str.strip()
        )

        df.loc[
            df[column].isin(["", "nan", "None", "<NA>"]),
            column
        ] = pd.NA

    # -----------------------------
    # Timestamp must exist
    # -----------------------------
    df = df[df["base_date_time"].notna()]

    # -----------------------------
    # Remove exact duplicate rows
    # -----------------------------
    df = df.drop_duplicates()

    return df


def process():
    validate_input()

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)

    TEMP_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    print("=" * 60)
    print("M3 AIS CLEANING PIPELINE")
    print("=" * 60)
    print(f"Input : {INPUT_FILE}")
    print(f"Output: {OUTPUT_FILE}")
    print()

    part_files = []
    total_input = 0
    total_output = 0

    # chunksize makes read_csv return an iterator that yields one DataFrame per chunk
    reader = pd.read_csv(
        INPUT_FILE,
        compression="zstd",
        chunksize=CHUNK_SIZE,
        low_memory=False
    )

    for part_number, chunk in enumerate(reader, start=1):
        total_input += len(chunk)

        print(
            f"Processing chunk {part_number}: "
            f"{len(chunk):,} rows"
        )

        cleaned = clean_chunk(chunk)

        output_part = TEMP_DIR / (
            f"part_{part_number:05d}.parquet"
        )

        cleaned.to_parquet(
            output_part,
            index=False
        )

        part_files.append(output_part)
        total_output += len(cleaned)

        print(
            f"  cleaned: {len(cleaned):,} rows"
        )

    if not part_files:
        raise RuntimeError("No cleaned AIS data was produced.")

    print()
    print("Combining cleaned chunks...")

    # DuckDB performs the final global deduplication
    # and sorting without loading everything into pandas.
    # ROW_NUMBER() ... PARTITION BY mmsi, base_date_time numbers rows that share the same
    # ship + timestamp; keeping row_number = 1 keeps exactly one of each.
    con = duckdb.connect()

    part_pattern = str(TEMP_DIR / "*.parquet")

    con.execute(
        f"""
        COPY (
            SELECT *
            FROM (
                SELECT *,
                    ROW_NUMBER() OVER (
                        PARTITION BY mmsi, base_date_time
                        ORDER BY mmsi
                    ) AS row_number
                FROM read_parquet('{part_pattern}')
            )
            WHERE row_number = 1
            ORDER BY mmsi, base_date_time
        )
        TO '{OUTPUT_FILE}'
        (FORMAT PARQUET, COMPRESSION ZSTD);
        """
    )

    con.close()

    # Remove temporary chunks.
    shutil.rmtree(TEMP_DIR)

    print()
    print("=" * 60)
    print("CLEANING COMPLETE")
    print("=" * 60)
    print(f"Input rows processed : {total_input:,}")
    print(f"Rows after cleaning  : {total_output:,}")
    print(f"Output file          : {OUTPUT_FILE}")

    # Basic verification
    con = duckdb.connect()

    result = con.execute(
        f"""
        SELECT
            COUNT(*) AS rows,
            COUNT(DISTINCT mmsi) AS vessels,
            MIN(base_date_time) AS earliest_timestamp,
            MAX(base_date_time) AS latest_timestamp
        FROM read_parquet('{OUTPUT_FILE}')
        """
    ).fetchone()

    con.close()

    print()
    print("========== OUTPUT CHECK ==========")
    print(f"Rows       : {result[0]:,}")
    print(f"Vessels    : {result[1]:,}")
    print(f"Earliest   : {result[2]}")
    print(f"Latest     : {result[3]}")


if __name__ == "__main__":
    process()
