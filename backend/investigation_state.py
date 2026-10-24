"""
investigation_state.py - Holds all the data for an investigation while the server runs.

Think of an InvestigationState object as the "case file". Every endpoint in app.py
reads from it and writes its results into it:
    upload  -> fills evidence + detection fields
    hindcast -> fills origin fields
    forecast -> fills forecast fields
    report  -> reads everything

Storage is in memory only (a Python dict), so all data is lost when the server restarts,
and every browser connected to the server shares the same "current" investigation.
"""
import uuid
import math
import numpy as np
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

class InvestigationState:
    """
    Encapsulates isolated state for a single AQUA SHIELD V2 investigation.
    No global mutable investigation state is shared between instances.
    """
    def __init__(self, investigation_id: Optional[str] = None):
        # Unique case ID like "INV-3FA9C2" (6 random hex characters from a UUID)
        self.investigation_id = investigation_id or f"INV-{uuid.uuid4().hex[:6].upper()}"
        self.created_at = datetime.utcnow().isoformat() + "Z"   # "Z" = UTC time zone
        self.status = "NEW"

        # Evidence / Image metadata
        self.evidence_filename: Optional[str] = None
        self.evidence_path: Optional[Path] = None
        self.has_georef: bool = False                 # True if we know where on Earth the image is
        self.crs: Optional[str] = None                # Coordinate Reference System, e.g. "EPSG:4326" (= normal lat/lng)
        self.geotransform: Optional[List[float]] = None
        self.bounds: Optional[Dict[str, float]] = None  # {min_lat, max_lat, min_lng, max_lng}

        # M2 Detection state (filled after the U-Net spill detector runs)
        self.m2_ran: bool = False
        self.center_lat: Optional[float] = None       # center of the image / spill
        self.center_lng: Optional[float] = None
        self.spill_area_km2: float = 0.0
        self.oil_pixels: int = 0                      # number of pixels classified as oil
        self.mean_probability: float = 0.0            # average model confidence over oil pixels (0-1)
        self.max_probability: float = 0.0
        self.spill_polygon: List[List[float]] = []  # [[lat, lng], ...]  outline drawn on the map
        self.bounding_box: Optional[List[float]] = None
        self.classification: str = "UNCLASSIFIED (SAR DARK SPOT)"
        self.model_warning: str = "M2 MODEL: PyTorch U-Net | VAL DICE: 7.94% | HIGH FALSE-POSITIVE WARNING"

        # M4 Drift / Ocean state (filled by hindcast + forecast)
        self.m4_hindcast_ran: bool = False
        self.origin_lat: Optional[float] = None       # reconstructed discharge point
        self.origin_lng: Optional[float] = None
        self.uncertainty_radius_km: float = 8.6
        self.hindcast_trajectory: List[Dict[str, Any]] = []
        # Default ocean conditions shown in the UI (uo/vo = east/north current speed in m/s)
        self.ocean_forcing: Dict[str, Any] = {
            "uo": 0.35, "vo": -0.22, "speed_kn": 1.42, "direction": "SE (135°)",
            "sst_c": 28.4, "wind": "--", "wave": "--"
        }
        self.m4_forecast_ran: bool = False
        self.forecast_polygon: List[List[float]] = []
        self.forecast_area_km2: float = 0.0
        self.forecast_notice: str = "OBSERVED OCEAN FORCING"

        # AIS state (ship tracking)
        self.ais_mode: str = "HISTORICAL" # HISTORICAL, LIVE, RECORDED_DEMO
        self.historical_candidates_count: int = 0
        self.historical_notice: str = "INSUFFICIENT SPATIO-TEMPORAL AIS COVERAGE"
        self.live_vessels: List[Dict[str, Any]] = []
        self.recorded_demo_vessels: List[Dict[str, Any]] = []
        self.selected_recorded_vessel: Optional[Dict[str, Any]] = None
        # Set when the uploaded image is a bundled test scene with a known vessel track
        self.real_ais_match: Optional[Dict[str, Any]] = None

        # Report & Data Health
        self.report_generated: bool = False
        self.report_dossier: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converts the whole case file into a nested dictionary so it can be sent as JSON."""
        return {
            "investigation_id": self.investigation_id,
            "created_at": self.created_at,
            "status": self.status,
            "evidence": {
                "filename": self.evidence_filename,
                "has_georef": self.has_georef,
                "crs": self.crs,
                "bounds": self.bounds
            },
            "spill_detection": {
                "ran": self.m2_ran,
                "center_lat": self.center_lat,
                "center_lng": self.center_lng,
                "area_km2": self.spill_area_km2,
                "oil_pixels": self.oil_pixels,
                "mean_probability": self.mean_probability,
                "max_probability": self.max_probability,
                "classification": self.classification,
                "model_warning": self.model_warning,
                "polygon": self.spill_polygon
            },
            "ocean_drift": {
                "hindcast_ran": self.m4_hindcast_ran,
                "origin_lat": self.origin_lat,
                "origin_lng": self.origin_lng,
                "uncertainty_radius_km": self.uncertainty_radius_km,
                "hindcast_trajectory": self.hindcast_trajectory,
                "ocean_forcing": self.ocean_forcing,
                "forecast_ran": self.m4_forecast_ran,
                "forecast_polygon": self.forecast_polygon,
                "forecast_area_km2": self.forecast_area_km2,
                "forecast_notice": self.forecast_notice
            },
            "ais": {
                "mode": self.ais_mode,
                "historical_candidates_count": self.historical_candidates_count,
                "historical_notice": self.historical_notice,
                "live_vessels_count": len(self.live_vessels),
                "recorded_vessels_count": len(self.recorded_demo_vessels)
            },
            "data_health": self.get_data_health()
        }

    def get_data_health(self) -> Dict[str, Dict[str, Any]]:
        """
        Status lights for the "Data Health" panel in the UI.
        Each entry has a text status and ok=True/False (green/red).
        NOTE: ocean_data and live_ais are always reported OK, and historical_ais /
        attribution are always reported as not OK - they are fixed, not checked.
        """
        return {
            "satellite": {
                "status": "AVAILABLE" if self.evidence_filename else "NOT_LOADED",
                "ok": bool(self.evidence_filename)
            },
            "georeferencing": {
                "status": "VERIFIED" if self.has_georef else "UNAVAILABLE",
                "ok": self.has_georef
            },
            "m2_model": {
                "status": "HIGH FALSE-POSITIVE WARNING (Val Dice 7.94%)" if self.m2_ran else "READY",
                "ok": True,
                "warning": True
            },
            "ocean_data": {
                "status": "AVAILABLE",
                "ok": True
            },
            "m4_hindcast": {
                "status": "AVAILABLE" if self.m4_hindcast_ran else "READY",
                "ok": self.m4_hindcast_ran
            },
            "live_ais": {
                "status": "AVAILABLE",
                "ok": True
            },
            "historical_ais": {
                "status": "INSUFFICIENT COVERAGE",
                "ok": False
            },
            "attribution": {
                "status": "NOT ELIGIBLE (0 Verified Historical Candidates)",
                "ok": False
            }
        }

# Global in-memory storage of active investigations
# _ACTIVE_INVESTIGATIONS maps case ID -> InvestigationState.
# _CURRENT_INVESTIGATION_ID remembers which case is currently open.
# (Leading underscore = "private to this module" by Python convention.)
_ACTIVE_INVESTIGATIONS: Dict[str, InvestigationState] = {}
_CURRENT_INVESTIGATION_ID: Optional[str] = None

def get_current_investigation() -> InvestigationState:
    """Returns the open case. If none exists yet (first request after startup), creates one."""
    global _CURRENT_INVESTIGATION_ID, _ACTIVE_INVESTIGATIONS
    if _CURRENT_INVESTIGATION_ID is None or _CURRENT_INVESTIGATION_ID not in _ACTIVE_INVESTIGATIONS:
        inv = InvestigationState()
        _ACTIVE_INVESTIGATIONS[inv.investigation_id] = inv
        _CURRENT_INVESTIGATION_ID = inv.investigation_id
    return _ACTIVE_INVESTIGATIONS[_CURRENT_INVESTIGATION_ID]

def create_new_investigation() -> InvestigationState:
    """Starts a fresh case and makes it the current one (the old case stays in memory)."""
    global _CURRENT_INVESTIGATION_ID, _ACTIVE_INVESTIGATIONS
    inv = InvestigationState()
    _ACTIVE_INVESTIGATIONS[inv.investigation_id] = inv
    _CURRENT_INVESTIGATION_ID = inv.investigation_id
    return inv
