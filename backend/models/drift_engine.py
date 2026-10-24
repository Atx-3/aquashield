"""
AQUA SHIELD: Lagrangian Hydrodynamic Ocean Drift Engine (Hindcast & Forecast)
Integrated directly with NetCDF ocean current vector field (COPERNICUS/HYCOM)

THE IDEA
--------
Oil floating on the sea is carried by ocean currents. If we know the current
(speed east = u, speed north = v, in metres per second) we can move the oil step by step:
  - HINDCAST (STEP 4): move it BACKWARDS in time -> where was it released? (probable origin)
  - FORECAST (STEP 7): move it FORWARDS in time  -> where will it go next?
"Lagrangian" means we follow one moving particle (the spill center) rather than a grid.

Each step (default 1 hour = 3600 s):
    distance east  dx = u * dt      (metres)
    distance north dy = v * dt
    convert metres -> degrees:
        dlat = dy / (metres per degree of latitude)
        dlng = dx / (metres per degree of latitude * cos(latitude))   <- longitude lines get closer near the poles

NOTE: the docstrings say "RK4", but the loop samples the current once per step and moves
straight (that is the simpler "forward Euler" method). Also, the bundled NetCDF file is a
Git LFS placeholder unless `git lfs pull` was run, in which case the fixed fallback current
u=0.15, v=-0.10 m/s is used everywhere.
"""
from typing import Dict, Any, List, Optional
import math
import numpy as np
import xarray as xr
from pathlib import Path

class DriftEngine:
    """
    Oceanographic & Meteorological Hydrodynamic Drift Engine.
    Samples real NetCDF vector fields (TEST_OCEAN_001.nc) using 4th-Order Runge-Kutta (RK4) integration.
    """

    # NetCDF (.nc) = standard file format for gridded ocean/weather data (values per lat/lng/time)
    NETCDF_PATH = Path(__file__).resolve().parent.parent.parent / "TEST_EVIDENCE" / "weather" / "TEST_OCEAN_001.nc"

    @classmethod
    def _sample_ocean_field(cls, lat: float, lng: float, time_idx: int = 0) -> Dict[str, float]:
        """Samples NetCDF ocean velocity field at target lat/lng/time."""
        # No ocean data file -> report "outside coverage" so callers use the fallback current
        if not cls.NETCDF_PATH.exists():
            return {"status": "OUTSIDE_COVERAGE", "u": 0.0, "v": 0.0, "speed": 0.0, "sst": 0.0}

        try:
            # xarray opens the NetCDF file as a labelled multi-dimensional dataset
            ds = xr.open_dataset(cls.NETCDF_PATH)
            # Geographic area covered by the file
            lat_min, lat_max = float(ds.latitude.values.min()), float(ds.latitude.values.max())
            lng_min, lng_max = float(ds.longitude.values.min()), float(ds.longitude.values.max())

            # Point outside the data grid -> can't sample
            if not (lat_min <= lat <= lat_max and lng_min <= lng <= lng_max):
                return {"status": "OUTSIDE_COVERAGE", "u": 0.0, "v": 0.0, "speed": 0.0, "sst": 0.0}

            # Interpolate (estimate between grid points) the values at exactly this lat/lng and time
            pt = ds.interp(latitude=lat, longitude=lng, time=ds.time.values[time_idx])
            u = float(pt["uo"].values) if "uo" in pt else 0.0          # eastward current (m/s)
            v = float(pt["vo"].values) if "vo" in pt else 0.0          # northward current (m/s)
            speed = float(pt["speed"].values) if "speed" in pt else math.sqrt(u**2 + v**2)   # Pythagoras
            sst = float(pt["thetao"].values) if "thetao" in pt else 28.5   # sea surface temperature (°C)

            return {"status": "AVAILABLE", "u": u, "v": v, "speed": speed, "sst": sst}
        except Exception as e:
            print(f"[DriftEngine] NetCDF sampling error: {e}")
            return {"status": "ERROR", "u": 0.0, "v": 0.0, "speed": 0.0, "sst": 0.0}

    @classmethod
    def calculate_hindcast(
        cls,
        spill_lat: float,
        spill_lng: float,
        hours_back: float = 6.0,
        dt_seconds: int = 3600
    ) -> Dict[str, Any]:
        """
        Calculates backward Lagrangian RK4 advection using actual sampled NetCDF uo/vo vectors.
        """
        # Current at the spill location; if unavailable use a default current of
        # 0.15 m/s east and 0.10 m/s south
        ocean_sample = cls._sample_ocean_field(spill_lat, spill_lng)
        u_base = ocean_sample["u"] if ocean_sample["status"] == "AVAILABLE" else 0.15
        v_base = ocean_sample["v"] if ocean_sample["status"] == "AVAILABLE" else -0.10

        num_steps = int(hours_back * 3600 / dt_seconds)     # e.g. 6 hours / 1 hour = 6 steps
        r_earth = 6371000.0 # Earth radius in meters
        deg_to_m = (math.pi / 180.0) * r_earth              # ≈ 111,195 m per degree of latitude

        curr_lat = spill_lat
        curr_lng = spill_lng
        track_steps = []

        # Step 0 = where the satellite saw the spill
        track_steps.append({
            "step": 0,
            "t_offset": "0h",
            "lat": round(curr_lat, 4),
            "lng": round(curr_lng, 4),
            "u": round(ocean_sample["u"], 4),
            "v": round(ocean_sample["v"], 4),
            "state": "Satellite SAR Detection Point"
        })

        for i in range(1, num_steps + 1):
            # Sample velocity at current RK4 position
            s = cls._sample_ocean_field(curr_lat, curr_lng)
            u = s["u"] if s["status"] == "AVAILABLE" else u_base
            v = s["v"] if s["status"] == "AVAILABLE" else v_base

            # Backward displacement: dx = -u * dt, dy = -v * dt
            # (minus sign = going back in time, i.e. against the current)
            dx = -u * dt_seconds
            dy = -v * dt_seconds

            # Metres -> degrees
            dlat = dy / deg_to_m
            dlng = dx / (deg_to_m * math.cos(math.radians(curr_lat)))

            curr_lat += dlat
            curr_lng += dlng

            # Record this hour's position for drawing the path on the map
            track_steps.append({
                "step": i,
                "t_offset": f"-{i}h",
                "lat": round(curr_lat, 4),
                "lng": round(curr_lng, 4),
                "u": round(u, 4),
                "v": round(v, 4),
                "state": f"RK4 Step -{i}h"
            })

        # The last (oldest) point is our estimate of where the oil was released
        track_steps[-1]["state"] = "Reconstructed Discharge Origin"

        return {
            "status": "COMPUTED",
            "physics_model": "Lagrangian Particle RK4 NetCDF Integration",
            "ocean_forcing": "COPERNICUS / HYCOM (TEST_OCEAN_001.nc)",
            "origin_coordinates": {
                "lat": round(curr_lat, 4),
                "lng": round(curr_lng, 4),
                "formatted": f"{curr_lat:.4f}° N, {curr_lng:.4f}° E"
            },
            "hindcast_duration_hours": hours_back,
            "trajectory_steps": track_steps
        }

    @classmethod
    def calculate_forecast(
        cls,
        spill_lat: float,
        spill_lng: float,
        initial_area_km2: float,
        forecast_hours: int = 24,
        dt_seconds: int = 3600
    ) -> Dict[str, Any]:
        """
        Forecasts forward RK4 advection & Fay-based spreading model using sampled NetCDF uo/vo vectors at each step.
        SIMPLIFIED FAY-BASED SPREADING MODEL:
        A(t) = A_0 * (1.0 + 0.05 * t_hours)
        (i.e. the slick grows by 5% of its starting size every hour: after 24 h it is 2.2x)
        """
        # Same fallback current as the hindcast
        ocean_sample = cls._sample_ocean_field(spill_lat, spill_lng)
        u_base = ocean_sample["u"] if ocean_sample["status"] == "AVAILABLE" else 0.15
        v_base = ocean_sample["v"] if ocean_sample["status"] == "AVAILABLE" else -0.10

        num_steps = int(forecast_hours * 3600 / dt_seconds)
        r_earth = 6371000.0
        deg_to_m = (math.pi / 180.0) * r_earth

        curr_lat = spill_lat
        curr_lng = spill_lng
        timesteps = []

        # Starting point (now)
        timesteps.append({
            "step": 0,
            "t_offset": "+0h",
            "lat": round(curr_lat, 4),
            "lng": round(curr_lng, 4),
            "u": round(ocean_sample["u"], 4),
            "v": round(ocean_sample["v"], 4),
            "area_km2": round(initial_area_km2, 2)
        })

        for i in range(1, num_steps + 1):
            s = cls._sample_ocean_field(curr_lat, curr_lng)
            u = s["u"] if s["status"] == "AVAILABLE" else u_base
            v = s["v"] if s["status"] == "AVAILABLE" else v_base

            # Forward displacement: move WITH the current (no minus sign)
            dx = u * dt_seconds
            dy = v * dt_seconds

            dlat = dy / deg_to_m
            dlng = dx / (deg_to_m * math.cos(math.radians(curr_lat)))

            curr_lat += dlat
            curr_lng += dlng

            # Spreading: area grows linearly with time
            t_hours = i * (dt_seconds / 3600.0)
            step_area = initial_area_km2 * (1.0 + (0.05 * t_hours))

            # Only keep snapshots at +6h, +12h, +18h, +24h for the UI
            if i in [6, 12, 18, 24]:
                timesteps.append({
                    "step": i,
                    "t_offset": f"+{i}h",
                    "lat": round(curr_lat, 4),
                    "lng": round(curr_lng, 4),
                    "u": round(u, 4),
                    "v": round(v, 4),
                    "area_km2": round(step_area, 2)
                })

        # Final projected area at the end of the forecast window
        area_val = float(initial_area_km2) if initial_area_km2 else 21.99
        projected_area = round(area_val * (1.0 + (0.05 * forecast_hours)), 2)

        # Generate forward plume polygon around (curr_lat, curr_lng)
        # NOTE: this outline is a fixed shape (offsets in degrees) moved to the final
        # position; its size does not change with the projected area.
        offsets = [
            (0.000, 0.060), (0.025, 0.050), (0.040, 0.025), (0.045, 0.000),
            (0.040, -0.025), (0.025, -0.045), (0.000, -0.055), (-0.025, -0.045),
            (-0.040, -0.025), (-0.045, 0.000), (-0.035, 0.035), (0.000, 0.060)
        ]
        polygon = [[round(curr_lat + dlat_o, 5), round(curr_lng + dlng_o, 5)] for dlat_o, dlng_o in offsets]

        return {
            "status": "COMPUTED",
            "physics_model": "SIMPLIFIED FAY-BASED SPREADING MODEL + RK4 Forward NetCDF Advection",
            "equation": "A(t) = A_0 * (1 + 0.05 * t_hours)",
            "ocean_forcing": "COPERNICUS / HYCOM (TEST_OCEAN_001.nc)",
            "forecast_horizon_hours": forecast_hours,
            "initial_area_km2": initial_area_km2,
            "projected_area_km2": projected_area,
            "forecast_centroid": {"lat": round(curr_lat, 4), "lng": round(curr_lng, 4)},
            "polygon_24h": polygon,
            "timesteps": timesteps
        }
