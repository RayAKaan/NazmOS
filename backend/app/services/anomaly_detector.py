import numpy as np
from typing import List, Dict
from datetime import datetime


class AnomalyDetector:
    def detect_anomalies(
        self,
        item_id: str,
        item_name: str,
        daily_sales: List[Dict],
        threshold_z: float = 2.5
    ) -> List[Dict]:
        if len(daily_sales) < 14:
            return []

        values = [d.get("quantity", 0) for d in daily_sales]
        mean = np.mean(values)
        std = np.std(values)

        if std == 0:
            return []

        anomalies = []
        for day in daily_sales:
            qty = day.get("quantity", 0)
            z_score = (qty - mean) / std if std > 0 else 0

            if abs(z_score) > threshold_z:
                anomalies.append({
                    "item_id": item_id,
                    "item_name": item_name,
                    "type": "spike" if z_score > 0 else "drop",
                    "magnitude_pct": round(abs(z_score) * 20, 1),
                    "date": day.get("date"),
                    "value": qty,
                    "expected_value": round(mean, 1),
                    "z_score": round(z_score, 2),
                })

        return anomalies

    def calculate_trend_strength(
        self,
        recent_14_days: List[float],
        prior_14_days: List[float]
    ) -> Dict:
        if not recent_14_days or not prior_14_days:
            return {"direction": "stable", "strength_pct": 0}

        recent_avg = np.mean(recent_14_days)
        prior_avg = np.mean(prior_14_days)

        if prior_avg == 0:
            return {"direction": "stable", "strength_pct": 0}

        change_pct = ((recent_avg - prior_avg) / prior_avg) * 100

        if change_pct > 10:
            direction = "up"
        elif change_pct < -10:
            direction = "down"
        else:
            direction = "stable"

        return {
            "direction": direction,
            "strength_pct": round(abs(change_pct), 1),
            "recent_avg": round(recent_avg, 2),
            "prior_avg": round(prior_avg, 2),
            "change_pct": round(change_pct, 1),
        }
