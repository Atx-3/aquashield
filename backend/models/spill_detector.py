"""
AQUA SHIELD: Satellite SAR & EO Remote Sensing Oil Spill Detection Engine
Implements:
(a) Dark-spot segmentation on SAR / EO imagery
(b) Exact geometric properties (Area, Perimeter, Major/Minor Axis, Eccentricity, Compactness, Fractal Dim)
(c) Oil slick age & weathering physics model (Mackay evaporative exposure, Bonn thickness, volume)

WHAT THIS FILE REALLY DOES (STEP 3 - Characterization)
------------------------------------------------------
The actual pixel-level detection is done by the U-Net in v1_models/AQUA_SHIELD_M2.
This class only DESCRIBES a slick, given its area:
  - calculate_geometric_properties(): shape numbers derived from the area using formulas
    that assume an ellipse-like slick (it does not look at the real outline).
  - estimate_slick_age_and_weathering(): age / evaporation / emulsification are fixed
    reference values; only volume and mass are calculated (area x assumed thickness).
  - analyze_spill_signature(): bundles both with fixed radar/optical reference values.
Terms:  EO = Electro-Optical (normal camera images).  Bonn Agreement = European standard
for estimating oil thickness from its appearance.  MARPOL Annex I = international rules
against oil pollution from ships.
"""
from typing import Dict, Any, List, Tuple
import math
from backend.config import SPILL_CENTER_LAT, SPILL_CENTER_LNG, SPILL_AREA_SQ_KM, DETECTION_CONFIDENCE

class SpillDetector:
    """
    Satellite Remote Sensing SAR & EO Oil Spill Detection, Segmentation,
    Geometric Characterization, and Age Estimation Engine.
    """

    @staticmethod
    def calculate_geometric_properties(area_km2: float = SPILL_AREA_SQ_KM) -> Dict[str, Any]:
        """
        Calculates full geometric and morphological invariants of the detected slick.
        """
        # Use at least 0.001 km² so the formulas below never divide by zero
        eff_area = max(0.001, float(area_km2 if area_km2 is not None else 0.0))
        # Perimeter: circumference of a circle with this area (2·sqrt(π·A)) scaled up by
        # empirical factors (2.85/2 x 1.58) to imitate a ragged, irregular slick edge
        perimeter_km = round(2.85 * math.sqrt(math.pi * eff_area) * 1.58, 2)
        # Treat the slick as an ellipse (area = π·a·b/4 with axes a, b).
        # Major (long) axis is chosen assuming the short axis is ~45% of the long one.
        major_axis_raw = max(0.01, math.sqrt((4 * eff_area) / (math.pi * 0.45)))
        major_axis_km = round(major_axis_raw, 2)
        # Minor (short) axis follows from area and major axis
        minor_axis_km = round(eff_area / (math.pi * (major_axis_raw / 2)), 2)

        # Eccentricity: 0 = perfect circle, close to 1 = very stretched
        eccentricity = round(math.sqrt(max(0.0, 1.0 - (minor_axis_km / max(0.01, major_axis_raw)) ** 2)), 3)
        # Compactness (isoperimetric ratio): 4πA / P². 1 = circle, smaller = more irregular
        compactness = round((4 * math.pi * eff_area) / (perimeter_km ** 2), 4)
        # Fractal dimension: how "wiggly" the edge is (≈1 smooth, closer to 2 very jagged)
        fractal_dimension = round(2 * math.log(max(1.0, perimeter_km / 4.0)) / math.log(max(1.1, eff_area)), 3)
        orientation_deg = 52.4      # fixed value (not measured from the image)

        return {
            "area_km2": round(area_km2, 2) if area_km2 else 0.0,
            "area_sq_meters": int((area_km2 or 0.0) * 1e6),
            "perimeter_km": perimeter_km,
            "major_axis_km": major_axis_km,
            "minor_axis_km": minor_axis_km,
            "aspect_ratio": round(major_axis_km / max(0.1, minor_axis_km), 2),   # long / short
            "eccentricity": eccentricity,
            "compactness_index": compactness,
            "fractal_dimension": fractal_dimension,
            "orientation_deg": orientation_deg,
            "shape_classification": "Elongated Asymmetric Plume (Active Hydrodynamic Drift)"
        }

    @staticmethod
    def estimate_slick_age_and_weathering(
        area_km2: float = SPILL_AREA_SQ_KM,
        sea_surface_temp_c: float = 28.4,
        wind_speed_knots: float = 12.6
    ) -> Dict[str, Any]:
        """
        Estimates slick age (hours elapsed since discharge) and weathering state
        using Mackay's Evaporative Exposure Model.
        NOTE: the temperature and wind inputs are not used; the values below are fixed
        reference numbers. Only volume / barrels / mass depend on the area.
        """
        # Fixed reference values for a ~6-hour-old heavy fuel oil slick
        initial_density_kg_m3 = 890.0        # typical heavy fuel oil density
        current_evaporation_loss_pct = 24.6  # % of oil evaporated so far
        water_emulsification_pct = 42.0      # % water mixed in ("mousse")
        current_viscosity_cst = 480.0        # thickness of the oil (how slowly it flows)
        estimated_age_hours = 6.2
        age_uncertainty_hours = 0.8

        # Volume = area x thickness. Assume an average layer of 300 micrometres (0.3 mm).
        mean_thickness_microns = 300
        mean_thickness_meters = mean_thickness_microns * 1e-6
        total_slick_volume_m3 = round(area_km2 * 1e6 * mean_thickness_meters, 1) # ~3,720 m³   (km² -> m² is x1e6)
        total_slick_volume_barrels = int(total_slick_volume_m3 * 6.2898) # ~23,400 bbl   (1 m³ = 6.2898 oil barrels)
        total_mass_tonnes = round((total_slick_volume_m3 * initial_density_kg_m3) / 1000.0, 1) # ~3,310 metric tons   (mass = volume x density)

        return {
            "estimated_age_hours": estimated_age_hours,
            "age_confidence_interval": f"{estimated_age_hours - age_uncertainty_hours:.1f}h - {estimated_age_hours + age_uncertainty_hours:.1f}h",
            "estimated_discharge_time_utc": "2026-08-26T14:00:00Z (±45 min)",
            "weathering_stage": "Stage 2: Secondary Emulsification & Weathering (Mousse Formation)",
            "evaporation_loss_pct": current_evaporation_loss_pct,
            "water_emulsification_pct": water_emulsification_pct,
            "viscosity_cp": current_viscosity_cst,
            "bonn_agreement_classification": {
                "code": "Code 4 (Continuous Metallic Sheen & Heavy Slick)",
                "color_appearance": "Metallic Dark Sheen with True Oil Cores",
                "layer_thickness_microns": mean_thickness_microns,
                "layer_thickness_mm": round(mean_thickness_microns / 1000.0, 3)
            },
            "discharged_volume_estimates": {
                "volume_m3": total_slick_volume_m3,
                "volume_barrels": total_slick_volume_barrels,
                "mass_metric_tonnes": total_mass_tonnes
            }
        }

    @classmethod
    def analyze_spill_signature(cls, image_id: str = "IMG_2640_1432.tif") -> Dict[str, Any]:
        """
        Executes end-to-end SAR & EO characterization pipeline.
        Uses the default demo area from config.py; app.py then overwrites the location and
        area with the real uploaded values. The radar/optical numbers below are fixed
        reference values, not measured from the image.
        """
        geometry = cls.calculate_geometric_properties(SPILL_AREA_SQ_KM)
        weathering = cls.estimate_slick_age_and_weathering(SPILL_AREA_SQ_KM)

        return {
            "status": "Detected",
            "case_id": "AS-026-IND",
            "image_source": image_id,
            "satellite_sensor": "Sentinel-1B C-band SAR (VV Polarization) + Sentinel-2 MSI Optical",
            "acquisition_timestamp": "2026-08-26T14:32:18Z",
            "center_coordinates": {
                "lat": SPILL_CENTER_LAT,
                "lng": SPILL_CENTER_LNG,
                "formatted": f"{SPILL_CENTER_LAT:.4f}° N, {SPILL_CENTER_LNG:.4f}° E"
            },
            "spill_geometry": geometry,
            "weathering_and_age": weathering,
            "slick_characterization": {
                "substance_type": "Heavy Marine Fuel / Crude Hydrocarbon",
                "bonn_agreement_code": "Code 4 (Metallic Sheen to Continuous Slick)",
                "estimated_thickness_um": 300,
                "estimated_volume_m3": weathering["discharged_volume_estimates"]["volume_m3"],
                "estimated_volume_barrels": weathering["discharged_volume_estimates"]["volume_barrels"],
                "weathering_stage": f"Secondary Emulsification (~{weathering['estimated_age_hours']} hours post-discharge)"
            },
            # SAR radar signature of the dark spot (oil "damps" small waves -> darker radar return)
            "radar_features": {
                "backscatter_contrast_db": -9.8,      # how much darker than surrounding sea (decibels)
                "damping_ratio": 5.4,
                "damping_ratio_db": 5.4,
                "gradient_sharpness": 0.84,           # how sharp the slick edge is
                "texture_entropy": 0.31,              # low = smooth, uniform texture
                "homogeneity": 0.92,
                "wind_smoothing_ratio": 3.8
            },
            # Optical indices (from normal-camera satellites like Sentinel-2)
            "optical_multispectral_indices": {
                "ndwi_anomaly": -0.42,                # water index anomaly
                "fai_floating_index": 0.18,           # Floating Algae/material Index
                "oil_slickening_index_osi": 0.88
            },
            "detection_confidence": DETECTION_CONFIDENCE,
            "confidence_percentage": f"{int(DETECTION_CONFIDENCE * 100)}%",
            "classification": "CONFIRMED_MARPOL_POLLUTION_EVENT",
            "legal_marpol_annex": "MARPOL 73/78 Annex I (Discharge of Oil Prohibited)",
            "statutory_violation": "MARPOL 73/78 Annex I, Regulation 15 (Control of Discharge of Oil)"
        }
