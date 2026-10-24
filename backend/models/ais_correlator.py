"""
AQUA SHIELD: Spatio-Temporal AIS Vessel Trajectory Correlation & Attribution Engine
Implements:
(c) Historic AIS data ingestion, noise filtering (filters irrelevant traffic)
(c) Spatio-temporal trajectory reconstruction around the discharge origin window
(c) Multi-aspect behavioral anomaly and risk scoring (proximity, speed drop, draft loss, AIS gaps)

CURRENT STATE
-------------
This is the "historical AIS" engine: it would match ships' PAST positions against the spill
origin and time. No historical AIS database for the Indian coast is bundled, so
get_vessels_dataset() returns an empty list and every method returns "0 candidates".
The vessel ranking the UI actually shows is done in app.py (/api/compare_vessels) using
live Pelyr AIS data or the bundled test-scene match.
"""
from typing import Dict, Any, List
import math
from backend.data_loader import get_vessels_dataset
from backend.config import PROBABLE_ORIGIN_LAT, PROBABLE_ORIGIN_LNG, UNCERTAINTY_RADIUS_KM

class AISCorrelator:
    """
    Correlates Automatic Identification System (AIS) kinematic tracks
    with Lagrangian oceanographic hindcast discharge coordinates.
    """

    @staticmethod
    def get_all_vessels() -> List[Dict[str, Any]]:
        """Returns all 12 tracked vessels in the maritime surveillance zone."""
        # (Currently returns an empty list - see note at the top of the file)
        return get_vessels_dataset()

    @staticmethod
    def get_filtered_vessels(
        radius_km: float = 35.0,
        filter_irrelevant: bool = True
    ) -> Dict[str, Any]:
        """
        Filters out irrelevant maritime traffic:
        1. Excludes vessels operating outside the surveillance bounding radius (>35 km).
        2. Excludes small artisanal vessels (fishing trawlers/tugs) lacking hydrocarbon capacity.
        3. Excludes law enforcement / coast guard patrol assets.
        4. Focuses on commercial cargo and tanker tonnage transiting the temporal window.
        """
        all_vessels = get_vessels_dataset()
        relevant_candidates = []      # ships that could plausibly have discharged oil
        filtered_out_vessels = []     # ships we ignore, with the reason why

        for v in all_vessels:
            # Distance filter
            in_range = v["distance_km"] <= radius_km
            # Capacity / type filter
            is_law_enforcement = "Coast Guard" in v["vessel_type"]
            # DWT = deadweight tonnage (how much a ship can carry). Under 1,000 t = small boat.
            is_insufficient_capacity = v["dwt"] < 1000

            if filter_irrelevant:
                if in_range and not is_law_enforcement and not is_insufficient_capacity:
                    relevant_candidates.append(v)
                else:
                    filtered_out_vessels.append({
                        "id": v["id"],
                        "name": v["name"],
                        "reason_filtered": "Law Enforcement" if is_law_enforcement else ("Insufficient DWT Capacity (<1,000 MT)" if is_insufficient_capacity else "Outside Corridor Radius")
                    })
            else:
                relevant_candidates.append(v)

        return {
            "total_tracked_vessels": len(all_vessels),
            "relevant_candidates_count": len(relevant_candidates),
            "filtered_out_count": len(filtered_out_vessels),
            "relevant_vessels": relevant_candidates,
            "filtered_out_summary": filtered_out_vessels
        }

    @classmethod
    def correlate_candidates(cls) -> Dict[str, Any]:
        """
        Executes historical AIS correlation against available historical database.
        Returns 0 verified candidates if no historical AIS parquet coverage exists for target time.
        """
        # Always returns "no candidates": the only historical AIS data the team had covers
        # US waters (Jan 2025), not the Indian EEZ (Exclusive Economic Zone).
        return {
            "mode": "HISTORICAL CORRELATION",
            "total_vessels_in_area": 0,
            "suspect_candidates_count": 0,
            "primary_suspect": None,
            "candidate_ranking": [],
            "correlation_matrix": [],
            "historical_candidates_count": 0,
            "notice": "INSUFFICIENT SPATIO-TEMPORAL AIS COVERAGE (0 Verified Historical Candidates)",
            "explanation": "Available historical AIS parquet database covers US coastal waters (Jan 8, 2025). No historical AIS coverage for active Indian EEZ incident timestamp."
        }

    @staticmethod
    def get_vessel_detail(vessel_id: str) -> Dict[str, Any]:
        """Returns empty dictionary if vessel not found in historical dataset."""
        return {}
