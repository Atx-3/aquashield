"""
ais_manager.py - Loads pre-recorded vessel tracks from JSON files (demo mode).

A "manifest" JSON file lists test cases (one per vessel); each vessel's track points
live in a separate file named trajectory_<MMSI>.json.
NOTE: the folder these paths point to (TEST_EVIDENCE/satellite/vessel_test_cases) is not
in the repo and nothing currently imports this module, so it is unused legacy code.
"""
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from backend.config import RECORDED_TRACKS_MANIFEST, RECORDED_TRACKS_DIR

def load_recorded_tracks_manifest() -> Dict[str, Any]:
    """Reads the manifest file; returns an empty list of test cases if the file is missing."""
    if not RECORDED_TRACKS_MANIFEST.exists():
        return {"test_cases": []}
    with open(RECORDED_TRACKS_MANIFEST, "r", encoding="utf-8") as f:
        return json.load(f)

def load_recorded_track_points(mmsi: str) -> Optional[Dict[str, Any]]:
    """Returns {metadata, points} for one vessel, or None if it isn't found."""
    manifest = load_recorded_tracks_manifest()
    # next(...) returns the first test case whose MMSI matches, or None if there is none
    track_info = next((t for t in manifest.get("test_cases", []) if t["vessel_mmsi"] == mmsi), None)
    if not track_info:
        return None

    file_path = RECORDED_TRACKS_DIR / f"trajectory_{mmsi}.json"
    if not file_path.exists():
        return None

    with open(file_path, "r", encoding="utf-8") as f:
        track_data = json.load(f)

    return {
        "metadata": track_info,
        "points": track_data.get("points", [])
    }
