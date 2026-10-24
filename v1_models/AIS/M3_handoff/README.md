# AQUA SHIELD — M3 AIS / Vessel Intelligence

M3 is the AIS and vessel-intelligence module of AQUA SHIELD.

## Purpose

Given a spill location and timestamp, M3:

1. Finds AIS observations near the spill.
2. Filters observations by time window.
3. Groups observations by vessel.
4. Ranks candidate vessels.
5. Returns vessel metadata.
6. Returns vessel trajectories as GeoJSON.

The output is consumed by other AQUA SHIELD modules, especially M5 for map visualization.

---

## Architecture

```text
AIS historical data
        |
        v
   AIS Cleaning
        |
        v
 ais_clean.parquet
        |
        +------------------+
        |                  |
        v                  v
 Nearby Vessel Query   Trajectory Builder
        |                  |
        v                  v
   Candidates       Trajectory Data
        |                  |
        +--------+---------+
                 |
                 v
             Ranking
                 |
                 v
             FastAPI
                 |
        +--------+---------+
        |                  |
        v                  v
       M1                 M5
    API contract      Map / GeoJSON
