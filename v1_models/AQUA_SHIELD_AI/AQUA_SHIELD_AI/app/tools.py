"""
AQUA SHIELD AI Tool Definitions and Interfaces.

Defines the 8 allowed investigation intents, their parameter schemas,
and helper validation routines.

These names must match the functions the backend can run
(see execute_aqua_shield_function in backend/voice_assistant.py).
TOOL_REGISTRY documents each tool's purpose and optional parameters; the router uses
ALLOWED_INVESTIGATION_INTENTS as its whitelist and sanitize_arguments() to clean values.
"""

from typing import Any, Dict, List, Optional, Set

# The exact 8 allowed investigation tools/intents in AQUA SHIELD AI
ALLOWED_INVESTIGATION_INTENTS: Set[str] = {
    "analyze_spill",
    "find_probable_origin",
    "find_nearby_vessels",
    "get_vessel_trajectory",
    "compare_vessels",
    "forecast_spill",
    "get_evidence",
    "generate_report",
}

# Full set of recognized intents including 'unsupported' fallback
# ("|" between two sets = union, i.e. all items from both)
ALL_ALLOWED_INTENTS: Set[str] = ALLOWED_INVESTIGATION_INTENTS | {"unsupported"}

# Tool specifications with descriptions and parameter expectations
TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "analyze_spill": {
        "description": "Analyze detected oil spill characteristics, slick area, thickness, or image features.",
        "parameters": {
            "spill_id": {"type": "string", "description": "Specific spill identifier if mentioned.", "required": False},
            "timestamp": {"type": "string", "description": "Time/date reference if mentioned.", "required": False},
        },
    },
    "find_probable_origin": {
        "description": "Perform reverse drift/backtracking to locate the probable source/origin location of the oil slick.",
        "parameters": {
            "spill_id": {"type": "string", "description": "Specific spill identifier if mentioned.", "required": False},
            "hours": {"type": "number", "description": "Number of hours to backtrack if specified.", "required": False},
        },
    },
    "find_nearby_vessels": {
        "description": "Search for ships/vessels in the vicinity of the spill location or specified area.",
        "parameters": {
            "radius_km": {"type": "number", "description": "Search radius in kilometers if specified (e.g., 20 for 20 km).", "required": False},
            "hours": {"type": "number", "description": "Time window in hours if specified.", "required": False},
            "spill_id": {"type": "string", "description": "Specific spill identifier if mentioned.", "required": False},
        },
    },
    "get_vessel_trajectory": {
        "description": "Retrieve AIS historical movement track or trajectory for a specific vessel.",
        "parameters": {
            "vessel_id": {"type": "string", "description": "Name, MMSI, or IMO of the vessel.", "required": False},
            "hours": {"type": "number", "description": "Time window in hours if specified.", "required": False},
        },
    },
    "compare_vessels": {
        "description": "Compare suspect vessels or evaluate multiple vessels against the spill timeline and corridor.",
        "parameters": {
            "vessel_ids": {"type": "list", "description": "List of vessel names or MMSIs to compare.", "required": False},
            "criteria": {"type": "string", "description": "Comparison criteria if specified.", "required": False},
        },
    },
    "forecast_spill": {
        "description": "Run forward drift simulation to predict the future trajectory and dispersion of the oil spill.",
        "parameters": {
            "forecast_hours": {"type": "number", "description": "Number of hours to forecast into the future (e.g., 24 for 24 hours).", "required": False},
            "spill_id": {"type": "string", "description": "Specific spill identifier if mentioned.", "required": False},
        },
    },
    "get_evidence": {
        "description": "Gather forensic evidence dossier, AIS logs, and satellite correlation proof for suspect ships.",
        "parameters": {
            "vessel_id": {"type": "string", "description": "Target vessel name or MMSI if mentioned.", "required": False},
            "spill_id": {"type": "string", "description": "Specific spill identifier if mentioned.", "required": False},
        },
    },
    "generate_report": {
        "description": "Generate an official investigation report, summary PDF, or audit export of the spill case.",
        "parameters": {
            "report_type": {"type": "string", "description": "Format or type of report (e.g. 'pdf', 'summary', 'full').", "required": False},
            "spill_id": {"type": "string", "description": "Specific spill identifier if mentioned.", "required": False},
        },
    },
}


def sanitize_arguments(intent: str, raw_args: Any) -> Dict[str, Any]:
    """
    Sanitize and validate extracted arguments:
    - Ensures raw_args is a dictionary.
    - Strips empty/null fields.
    - Converts numeric strings to actual numbers where appropriate (e.g., "20 km" -> 20 or "24" -> 24).
    - Prevents hallucinated or malformed structures.
    """
    if not isinstance(raw_args, dict):
        return {}

    sanitized: Dict[str, Any] = {}
    for key, value in raw_args.items():
        if value is None or value == "":
            continue

        # Clean key name
        clean_key = str(key).strip().lower()

        # Clean and type-cast common numeric fields
        if clean_key in {"radius_km", "hours", "forecast_hours", "backtrack_hours"}:
            if isinstance(value, (int, float)):
                sanitized[clean_key] = value
            elif isinstance(value, str):
                # Try extracting leading number, e.g. "20 km" -> 20
                num_str = "".join(ch for ch in value if ch.isdigit() or ch == ".")
                if num_str:
                    try:
                        sanitized[clean_key] = float(num_str) if "." in num_str else int(num_str)
                    except ValueError:
                        sanitized[clean_key] = value
                else:
                    sanitized[clean_key] = value
            else:
                sanitized[clean_key] = value
        else:
            sanitized[clean_key] = value

    return sanitized
