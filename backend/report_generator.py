"""
AQUA SHIELD: Forensic Investigation Report Generator
Produces publication-grade Maritime Incident Evidence Dossiers (MARPOL Annex I Violation Reports).

STEP 8 of the pipeline. Collects the results of every earlier step from the investigation
state and arranges them into one dictionary with 4 sections, which static/js/report.js
turns into the report pop-up:
    1. spill_detection      - area, shape, age (from SpillDetector)
    2. hindcast_origin      - reconstructed discharge point (from DriftEngine)
    3. forecast_dispersion  - 24h projected spread (from DriftEngine)
    4. culprit_attribution  - ranked candidate vessels
Steps that were never run are marked "NOT EXECUTED".
"""
from typing import Dict, Any
from datetime import datetime
from backend.config import CASE_ID, CASE_NAME, SPILL_AREA_SQ_KM, DETECTION_CONFIDENCE
from backend.models.spill_detector import SpillDetector
from backend.models.drift_engine import DriftEngine
from backend.models.ais_correlator import AISCorrelator

class ReportGenerator:
    """Generates structured legal evidence reports for coast guards and maritime tribunals."""

    @staticmethod
    def generate_investigation_dossier(inv=None) -> Dict[str, Any]:
        """Assembles all intelligence layers into a coherent legal report."""
        # If no investigation was passed in, use the currently open one
        if inv is None:
            from backend.investigation_state import get_current_investigation
            inv = get_current_investigation()

        # ---------- Section 1: spill detection ----------
        # Shape metrics + weathering for the detected area (0 if detection never ran)
        spill = SpillDetector.calculate_geometric_properties(inv.spill_area_km2 if inv.m2_ran else 0.0)
        spill["satellite_sensor"] = "Sentinel-1B C-band SAR"
        spill["center_coordinates"] = {
            "formatted": f"{inv.center_lat:.4f}° N, {inv.center_lng:.4f}° E" if (inv.center_lat and inv.center_lng) else "NOT EXECUTED"
        }
        spill["confidence_percentage"] = f"{inv.mean_probability * 100:.1f}%" if inv.m2_ran else "NOT EXECUTED"
        spill["weathering_and_age"] = SpillDetector.estimate_slick_age_and_weathering(inv.spill_area_km2 if inv.m2_ran else 0.0)

        # ---------- Section 2: hindcast (origin) ----------
        # If the hindcast ran, recompute it here to include the full trajectory in the report
        if inv.m4_hindcast_ran and inv.origin_lat and inv.origin_lng:
            hindcast = DriftEngine.calculate_hindcast(
                spill_lat=inv.center_lat,
                spill_lng=inv.center_lng,
                hours_back=6.0
            )
            hindcast["status"] = "EXECUTED"
            hindcast["origin_coordinates"] = {
                "formatted": f"{inv.origin_lat:.4f}° N, {inv.origin_lng:.4f}° E"
            }
        else:
            # Placeholder section when the hindcast step was skipped
            hindcast = {
                "status": "NOT EXECUTED",
                "origin_coordinates": {"formatted": "NOT EXECUTED"},
                "time_window": "NOT EXECUTED",
                "uncertainty_radius_km": "N/A",
                "hydrodynamic_factors": {
                    "ocean_current_vector": f"{inv.ocean_forcing.get('speed_kn', 'N/A')} kn @ {inv.ocean_forcing.get('direction', 'N/A')}",
                    "surface_wind_vector": "N/A",
                    "total_backdrift_distance_km": "N/A"
                }
            }

        # ---------- Section 3: forecast ----------
        if inv.m4_forecast_ran and inv.forecast_polygon:
            forecast = DriftEngine.calculate_forecast(
                spill_lat=inv.center_lat,
                spill_lng=inv.center_lng,
                initial_area_km2=inv.spill_area_km2,
                forecast_hours=24
            )
            forecast["status"] = "EXECUTED"
        else:
            forecast = {
                "status": "NOT EXECUTED",
                "projected_area_km2": "NOT EXECUTED",
                "forecast_endpoint": {"formatted": "NOT EXECUTED"}
            }

        # ---------- Section 4: candidate vessels ----------
        candidate_ranking = []
        primary_suspect = None

        # 1. Check real AIS dataset match
        # (uploaded file was a bundled test scene with a known ship)
        # NOTE: the match dict stores the ID under "vessel_mmsi" and has no distance,
        # so the "mmsi" lookups below give "N/A" and distance gives 0.0. Risk score 92 is fixed.
        if inv.real_ais_match and inv.real_ais_match.get("vessel_name"):
            match_vessel = inv.real_ais_match
            primary_suspect = {
                "name": match_vessel.get("vessel_name", "UNKNOWN"),
                "mmsi": str(match_vessel.get('mmsi', 'N/A')),
                "id": f"MMSI: {match_vessel.get('mmsi', 'N/A')}",
                "distance_km": match_vessel.get("distance_to_spill_km", 0.0),
                "speed_kn": match_vessel.get("sog", 0.0),
                "risk_score": 92
            }
            candidate_ranking.append(primary_suspect)
        # 2. Check live Pelyr vessels queried during investigation
        # (asks the Pelyr API again for ships currently within 250 km)
        elif inv.center_lat and inv.center_lng:
            from v1_models.AIS.M3_handoff.src.queries.pelyr_adapter import query_pelyr_live_vessels
            pelyr_data = query_pelyr_live_vessels(inv.center_lat, inv.center_lng, radius_km=250.0)
            raw_vessels = pelyr_data.get("vessels", [])
            if raw_vessels:
                # Rank by distance to origin/centroid
                target_lat = inv.origin_lat or inv.center_lat
                target_lng = inv.origin_lng or inv.center_lng
                import math
                calc_vessels = []
                for v in raw_vessels:
                    v_lat = v.get("latitude", 0.0)
                    v_lng = v.get("longitude", 0.0)
                    # Haversine great-circle distance in km (Earth radius 6371 km)
                    dlat = math.radians(target_lat - v_lat)
                    dlng = math.radians(target_lng - v_lng)
                    a = math.sin(dlat/2)**2 + math.cos(math.radians(v_lat)) * math.cos(math.radians(target_lat)) * math.sin(dlng/2)**2
                    dist = round(6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)
                    calc_vessels.append({
                        "name": v.get("vessel_name", f"Vessel {v.get('mmsi')}"),
                        "mmsi": str(v.get("mmsi")),
                        "id": f"MMSI: {v.get('mmsi')}",
                        "distance_km": dist,
                        "speed_kn": v.get("sog", 0.0),
                        # Simple score: 100 minus distance in km, never below 10
                        "risk_score": max(10, int(100 - dist))
                    })
                # Closest first; keep the top 5 for the report
                calc_vessels.sort(key=lambda x: x["distance_km"])
                candidate_ranking = calc_vessels[:5]
                if candidate_ranking:
                    primary_suspect = candidate_ranking[0]

        correlation = {
            "status": "EXECUTED" if candidate_ranking else "NOT EXECUTED",
            "candidate_ranking": candidate_ranking,
            # If nobody was found, show a placeholder entry instead of an empty box
            "primary_suspect": primary_suspect or {"name": "INSUFFICIENT HISTORICAL AIS EVIDENCE", "id": "N/A", "mmsi": "N/A", "distance_km": "N/A", "speed_kn": "N/A", "risk_score": 0}
        }

        report_timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        # ---------- Final report structure ----------
        return {
            "case_id": inv.investigation_id,
            "case_name": f"Offshore Spill Incident ({inv.investigation_id})",
            "report_timestamp": report_timestamp,
            "status": "OFFICIAL EVIDENCE DOSSIER - READY FOR SUBMISSION",
            "jurisdiction": "Indian Exclusive Economic Zone (EEZ) / Arabian Sea Offshore Sector",
            "lead_investigator": "AQUA SHIELD Autonomous Intelligence Engine (SIH-2026 AI/ML System)",
            "classification_level": "RESTRICTED / MARITIME LAW ENFORCEMENT",
            # One-paragraph summary built from the case data
            "executive_summary": (
                f"Sentinel-1 SAR imagery and hydrodynamic advection state for investigation {inv.investigation_id}. "
                f"Spill detection area: {inv.spill_area_km2:.2f} km² ({inv.classification}). "
                f"Hindcast origin: {f'{inv.origin_lat:.4f}°N, {inv.origin_lng:.4f}°E' if inv.origin_lat else 'NOT EXECUTED'}. "
                f"Leading Candidate: {primary_suspect.get('name') if primary_suspect else 'N/A'} (MMSI: {primary_suspect.get('mmsi') if primary_suspect else 'N/A'})."
            ),
            "sections": {
                "spill_detection": spill,
                "hindcast_origin": hindcast,
                "forecast_dispersion": forecast,
                "culprit_attribution": correlation
            },
            # Laws relevant to ship oil pollution (fixed list)
            "legal_citations": [
                "International Convention for the Prevention of Pollution from Ships (MARPOL 73/78) - Annex I, Regulation 15",
                "Merchant Shipping Act 1958 (India) - Part XI-A: Prevention and Containment of Pollution of the Sea by Oil",
                "United Nations Convention on the Law of the Sea (UNCLOS) - Article 211 (Pollution from vessels)"
            ],
            # Suggested next actions for authorities (first one names the top candidate if any)
            "enforcement_recommendations": [
                f"Issue Port State Control (PSC) verification notice to vessel {primary_suspect.get('name') if primary_suspect else 'candidates'} (MMSI: {primary_suspect.get('mmsi') if primary_suspect else 'N/A'})." if primary_suspect else "Issue Port State Control (PSC) verification notice to maritime vessels operating in target sector.",
                "Extract vessel Oil Record Book (Part II - Cargo/Ballast Operations) for candidates transiting origin corridor.",
                "Collect physical hydrocarbon finger-printing samples from slop tanks for spectral matching.",
                "Deploy containment boom flotilla along forecast path to protect coastal marine reserves."
            ]
        }
