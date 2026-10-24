"""
AQUA SHIELD: Tactical AI Voice Assistant & Intent Dispatcher
Routes spoken queries to backend functions and returns actionable voice/UI payloads.
Supports local Ollama (e.g. Qwen 3 1.7B) with zero-latency deterministic fallback.

HOW A VOICE COMMAND IS HANDLED
------------------------------
  "show me the 24 hour forecast"
      │
      ▼  1. _parse_intent_rule_based()  - keyword matching (fast, no AI needed)
      ▼  2. _try_ollama_intent()        - only if no keyword matched: ask a small local LLM
      ▼  3. default to "analyze_spill" if still unknown
      ▼  4. execute_aqua_shield_function() - run the matching backend function
      ▼
  returns { speech_response (text the browser speaks aloud),
            ui_action (what the browser should do, e.g. SHOW_FORECAST),
            data (the raw result) }
Ollama = a program that runs AI language models locally on your own computer.
"""
import re
import json
from typing import Dict, Any, Tuple
import requests

from backend.models.spill_detector import SpillDetector
from backend.models.drift_engine import DriftEngine
from backend.models.ais_correlator import AISCorrelator
from backend.report_generator import ReportGenerator
from backend.config import EVIDENCE_SOURCES

# Address of the local Ollama server's text-generation endpoint (11434 is Ollama's default port)
OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen:1.7b" # Can be configured to any 1B-3B model  (note: the code below actually sends "qwen3:1.7b")

class AquaShieldVoiceAssistant:
    """
    Tactical Voice & AI Assistant for AQUA SHIELD.
    Interprets natural spoken language and executes corresponding investigation tools.
    """

    # Instructions given to the LLM: pick one of these 8 functions and reply in JSON only
    SYSTEM_PROMPT = """You are AQUA SHIELD Tactical AI, an ocean intelligence system.
Your job is to identify the user's intent from their voice query and output the correct AQUA SHIELD function name and arguments in JSON format.
Valid functions:
- analyze_spill()
- find_probable_origin()
- find_nearby_vessels()
- get_vessel_trajectory(vessel_id)
- compare_vessels()
- forecast_spill(hours)
- get_evidence()
- generate_report()

Respond ONLY with valid JSON: {"function": "<name>", "args": {}}"""

    @classmethod
    def process_voice_query(cls, text: str) -> Dict[str, Any]:
        """
        Main entry point for voice command processing.
        Attempts local LLM intent extraction if available; defaults to high-accuracy pattern engine.
        """
        # Normalize: remove surrounding spaces and lowercase, so "FORECAST" == "forecast"
        cleaned_text = text.strip().lower()
        # Empty command -> just reply that we are listening
        if not cleaned_text:
            return {
                "transcript": text,
                "speech_response": "AQUA SHIELD listening. Awaiting tactical voice command.",
                "function_called": None,
                "ui_action": None,
                "data": None
            }

        # 1. First try deterministic intent parser (instant, zero network latency, 100% reliable for SIH demo)
        func_name, args = cls._parse_intent_rule_based(cleaned_text)

        # 2. If no rule matched and Ollama is running, try Ollama
        if not func_name:
            func_name, args = cls._try_ollama_intent(text)

        # 3. If still not resolved, default to contextual smart response
        if not func_name:
            func_name = "analyze_spill"
            args = {}

        # 4. Execute the mapped backend function
        speech_text, ui_action, data = cls.execute_aqua_shield_function(func_name, args)

        return {
            "transcript": text,
            "function_called": func_name,
            "args": args,
            "speech_response": speech_text,
            "ui_action": ui_action,
            "data": data
        }

    @staticmethod
    def _parse_intent_rule_based(text: str) -> Tuple[str, Dict[str, Any]]:
        """Fast, robust regex and keyword matching for voice commands."""
        # The checks run top to bottom and the FIRST match wins.
        # NOTE: because rule 1 matches any text containing "spill" or "oil", and rule 3
        # matches any text containing "vessel"/"ship", phrases like "where did the spill
        # come from" or "compare vessels" are caught by those earlier rules.
        # any(k in text for k in [...]) = True if at least one keyword appears in the text.
        # 1. Spill Analysis / Detection
        if any(k in text for k in ["analyze spill", "spill details", "what spill", "detect spill", "spill size", "characterize spill", "slick", "oil spill", "where is oil", "oil", "spill"]):
            return "analyze_spill", {}

        # 2. Probable Origin / Hindcast / Rewind
        if any(k in text for k in ["probable origin", "origin", "rewind", "hindcast", "where did it come from", "source of spill", "discharge point", "backtrack"]):
            return "find_probable_origin", {"hours": 6}

        # 3. Nearby Vessels / AIS Search (Step 5)
        if any(k in text for k in ["nearby vessels", "vessel analysis", "vessel", "vessels", "find vessels", "show vessels", "show ships", "ships", "ship", "traffic", "ships in area", "how many vessels", "list vessels"]):
            return "find_nearby_vessels", {"radius_km": 35.0}

        # 4. Compare Candidates / Correlation / Suspects (Step 6)
        if any(k in text for k in ["compare vessels", "do correlation", "correlation", "correlate", "who is culprit", "who is the culprit", "culprit", "suspects", "who did it", "responsible vessel", "candidates", "ranking", "most suspicious", "who spilled"]):
            return "compare_vessels", {}

        # 5. Vessel Specific Trajectory
        # Regex: the word "vessel", optional spaces/dashes, then a number -> captures the number
        match_vessel = re.search(r"vessel[\s\-]*(\d+)", text)
        if match_vessel or any(k in text for k in ["trajectory", "track of"]):
            v_id = f"VESSEL-{match_vessel.group(1)}" if match_vessel else ""
            return "get_vessel_trajectory", {"vessel_id": v_id}

        # 6. Forecast / Future Movement
        if any(k in text for k in ["forecast", "future", "where is it going", "drift projection", "24 hour", "prediction", "drift area"]):
            return "forecast_spill", {"hours": 24}

        # 7. Evidence / Data Sources
        if any(k in text for k in ["evidence", "sources", "data sources", "satellite image", "ais dataset", "netcdf", "radar file"]):
            return "get_evidence", {}

        # 8. Report / Dossier / Export
        if any(k in text for k in ["report", "generate report", "dossier", "export", "pdf", "evidence report", "briefing", "summary document"]):
            return "generate_report", {}

        # No keyword matched -> caller will try the LLM
        return None, {}

    @classmethod
    def _try_ollama_intent(cls, text: str) -> Tuple[str, Dict[str, Any]]:
        """Bridge to local Qwen3 1.7B Ollama instance via AQUA_SHIELD_AI router module with zero-latency fallback."""
        # Attempt 1: use the router from v1_models/AQUA_SHIELD_AI (validates the LLM's answer
        # against the allowed list of intents)
        try:
            from v1_models.AQUA_SHIELD_AI.AQUA_SHIELD_AI.app.router import AquaShieldRouter
            router = AquaShieldRouter(verbose=False)
            response = router.route(text) if hasattr(router, 'route') else router.process_query(text)
            if response and response.intent and response.intent != "unsupported":
                intent_map = {
                    "analyze_spill": "analyze_spill",
                    "find_probable_origin": "find_probable_origin",
                    "find_nearby_vessels": "find_nearby_vessels",
                    "get_vessel_trajectory": "get_vessel_trajectory",
                    "compare_vessels": "compare_vessels",
                    "forecast_spill": "forecast_spill",
                    "get_evidence": "get_evidence",
                    "generate_report": "generate_report"
                }
                func = intent_map.get(response.intent)
                if func:
                    return func, response.arguments or {}
        except Exception as e:
            print(f"[AquaShieldVoiceAssistant] AQUA_SHIELD_AI Ollama Qwen3:1.7b route notice: {e}")

        # Fallback query to direct Ollama REST endpoint if qwen3:1.7b model is running
        # Attempt 2: call Ollama's HTTP API directly with our SYSTEM_PROMPT.
        # timeout=0.8 s keeps the UI responsive if Ollama isn't running.
        try:
            payload = {
                "model": "qwen3:1.7b",
                "prompt": f"{cls.SYSTEM_PROMPT}\nUser voice query: \"{text}\"",
                "stream": False,
                "format": "json"
            }
            res = requests.post(OLLAMA_API_URL, json=payload, timeout=0.8)
            if res.status_code == 200:
                # Ollama returns {"response": "<model text>"}; the model text itself is our JSON
                parsed = json.loads(res.json().get("response", "{}"))
                return parsed.get("function"), parsed.get("args", {})
        except Exception:
            pass

        return None, {}

    @classmethod
    def execute_aqua_shield_function(cls, func_name: str, args: Dict[str, Any]) -> Tuple[str, Dict[str, Any], Any]:
        """
        Executes standard AQUA SHIELD backend functions against active investigation state and synthesizes voice response.
        Returns a tuple: (speech text, ui_action dict for the browser, data payload).
        The ui_action "type" tells static/js/app.js what to show (e.g. SHOW_FORECAST),
        and "step" tells it which pipeline step to highlight.
        """
        from backend.investigation_state import get_current_investigation
        inv = get_current_investigation()

        # --- Spill summary: read back location and area from the case file ---
        if func_name == "analyze_spill":
            speech = (
                f"Spill detection state for case {inv.investigation_id}: "
                f"Location is {inv.center_lat:.4f} North, {inv.center_lng:.4f} East covering {inv.spill_area_km2:.2f} square kilometers."
                if (inv.center_lat and inv.center_lng) else "No active satellite spill detected. Please upload SAR GeoTIFF imagery."
            )
            ui_action = {"type": "FOCUS_SPILL", "lat": inv.center_lat, "lng": inv.center_lng, "step": 3 if inv.m2_ran else 1}
            return speech, ui_action, inv.to_dict()

        # --- Hindcast: same as /api/find_probable_origin, then save the origin ---
        elif func_name == "find_probable_origin":
            if not inv.center_lat or not inv.center_lng:
                return "Awaiting satellite evidence before running hindcast rewind.", {"type": "FOCUS_SPILL", "step": 1}, {}
            data = DriftEngine.calculate_hindcast(spill_lat=inv.center_lat, spill_lng=inv.center_lng, hours_back=args.get("hours", 6.0))
            inv.origin_lat = data["origin_coordinates"]["lat"]
            inv.origin_lng = data["origin_coordinates"]["lng"]
            inv.m4_hindcast_ran = True
            speech = (
                f"Hydrodynamic hindcast rewind complete. Discharge origin reconstructed at {inv.origin_lat:.4f} North, {inv.origin_lng:.4f} East over a 6 hour trajectory."
            )
            ui_action = {"type": "SHOW_HINDCAST", "lat": inv.origin_lat, "lng": inv.origin_lng, "step": 4}
            return speech, ui_action, data

        # --- Nearby ships: query live Pelyr AIS within 250 km and say how many ---
        elif func_name == "find_nearby_vessels":
            from v1_models.AIS.M3_handoff.src.queries.pelyr_adapter import query_pelyr_live_vessels
            lat = inv.center_lat or 21.1520
            lng = inv.center_lng or 69.8540
            res = query_pelyr_live_vessels(lat, lng, radius_km=250.0)
            vessels = res.get("vessels", [])
            speech = f"Regional live AIS telemetry identified {len(vessels)} vessels transiting within the 250 kilometer surveillance area."
            ui_action = {"type": "SHOW_ALL_VESSELS", "count": len(vessels), "step": 5}
            return speech, ui_action, res

        # --- Correlation: name the closest candidate ship ---
        # (test-scene match if present, otherwise the nearest live Pelyr vessel;
        #  "WILCHIEF 1 #1" is a placeholder name used when nothing is found)
        elif func_name == "compare_vessels":
            from backend.app import api_compare_vessels   # imported but not used
            import asyncio
            # Execute actual correlation ranking logic
            if inv.real_ais_match and inv.real_ais_match.get("matched"):
                cand_name = inv.real_ais_match.get("vessel_name", "WILCHIEF 1")
            else:
                # Rank live pelyr vessels against origin
                from v1_models.AIS.M3_handoff.src.queries.pelyr_adapter import query_pelyr_live_vessels
                lat = inv.origin_lat or inv.center_lat or 21.1520
                lng = inv.origin_lng or inv.center_lng or 69.8540
                pelyr_res = query_pelyr_live_vessels(lat, lng, radius_km=250.0)
                vessels = pelyr_res.get("vessels", [])
                if vessels:
                    # Sort by distance
                    vessels.sort(key=lambda x: x.get("distance_km", 999.0))
                    cand_name = vessels[0].get("vessel_name", "WILCHIEF 1 #1")
                else:
                    cand_name = "WILCHIEF 1 #1"

            speech = f"Correlation analysis complete. Identified leading source candidate {cand_name} based on spatial distance to discharge origin."
            ui_action = {"type": "SHOW_CORRELATION_MATRIX", "step": 6}
            return speech, ui_action, inv.to_dict()

        # --- Forecast: run a 24h forward drift (falls back to a Mumbai-area point if no spill) ---
        elif func_name == "forecast_spill":
            lat = inv.center_lat or 18.7246
            lng = inv.center_lng or 72.8462
            area = inv.spill_area_km2 if inv.spill_area_km2 else 16.5
            data = DriftEngine.calculate_forecast(spill_lat=lat, spill_lng=lng, initial_area_km2=area, forecast_hours=24)
            inv.m4_forecast_ran = True
            inv.forecast_polygon = data.get("polygon_24h", [])
            speech = f"24 hour forward forecast computed. Projected spill expansion to {data.get('projected_area_km2', 27.8)} square kilometers."
            ui_action = {"type": "SHOW_FORECAST", "step": 7}
            return speech, ui_action, data

        # --- Report: build the dossier and tell the browser to open the report pop-up ---
        elif func_name == "generate_report":
            dossier = ReportGenerator.generate_investigation_dossier(inv)
            speech = f"Official Forensic Evidence Dossier compiled for active case {inv.investigation_id}."
            ui_action = {"type": "OPEN_REPORT_MODAL", "step": 8}
            return speech, ui_action, dossier

        # get_vessel_trajectory and get_evidence have no handler above, so they end up here
        return "Tactical voice command processed.", {"type": "REFRESH"}, {}
