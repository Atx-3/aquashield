"""
rank_candidates.py - Score and sort suspect ships (weighted-sum scoring).

Each ship gets four sub-scores between 0 and 1, combined with fixed weights:
    distance    40%   1.0 at the spill, falling to 0 at the edge of the search radius
    time        30%   1.0 at the spill time, falling to 0 at the edge of the time window
    trajectory  20%   currently always 1.0 (placeholder for future track analysis)
    vessel_type 10%   1.0 if the ship's type is known, 0.5 if not
final candidate_score = weighted sum x 100 (so 0..100); highest score first.
"""


def rank_candidates(candidates, radius_km=20, time_window_minutes=30):

    ranked = []

    for vessel in candidates:

        # 40% distance
        distance_score = max(
            0,
            1 - vessel["distance_km"] / radius_km
        )

        # 30% time
        time_score = max(
            0,
            1 - vessel["time_difference_minutes"] / time_window_minutes
        )

        # 20% trajectory confidence
        trajectory_score = 1.0

        # 10% vessel information availability
        vessel_type_score = (
            1.0
            if vessel.get("vessel_type") is not None
            else 0.5
        )

        final_score = (
            distance_score * 0.40
            + time_score * 0.30
            + trajectory_score * 0.20
            + vessel_type_score * 0.10
        )

        vessel["scores"] = {
            "distance": round(distance_score, 3),
            "time": round(time_score, 3),
            "trajectory": round(trajectory_score, 3),
            "vessel_type": round(vessel_type_score, 3),
        }

        vessel["candidate_score"] = round(final_score * 100, 2)

        ranked.append(vessel)

    # reverse=True -> highest score first
    return sorted(
        ranked,
        key=lambda x: x["candidate_score"],
        reverse=True
    )
