import pandas as pd
from datetime import date

FESTIVAL_DATES = [
    {"holiday": "diwali_prep", "ds": "2023-11-10", "lower_window": -2, "upper_window": 0},
    {"holiday": "diwali", "ds": "2023-11-12", "lower_window": 0, "upper_window": 1},
    {"holiday": "diwali_prep", "ds": "2024-10-31", "lower_window": -2, "upper_window": 0},
    {"holiday": "diwali", "ds": "2024-11-01", "lower_window": 0, "upper_window": 1},
    {"holiday": "diwali_prep", "ds": "2025-10-20", "lower_window": -2, "upper_window": 0},
    {"holiday": "diwali", "ds": "2025-10-21", "lower_window": 0, "upper_window": 1},
    {"holiday": "diwali_prep", "ds": "2026-10-09", "lower_window": -2, "upper_window": 0},
    {"holiday": "diwali", "ds": "2026-10-10", "lower_window": 0, "upper_window": 1},
    {"holiday": "holi", "ds": "2024-03-25", "lower_window": -1, "upper_window": 0},
    {"holiday": "holi", "ds": "2025-03-14", "lower_window": -1, "upper_window": 0},
    {"holiday": "holi", "ds": "2026-03-03", "lower_window": -1, "upper_window": 0},
    {"holiday": "eid", "ds": "2024-04-11", "lower_window": -2, "upper_window": 1},
    {"holiday": "eid", "ds": "2025-03-31", "lower_window": -2, "upper_window": 1},
    {"holiday": "eid", "ds": "2026-03-20", "lower_window": -2, "upper_window": 1},
    {"holiday": "pongal", "ds": "2024-01-15", "lower_window": -1, "upper_window": 0},
    {"holiday": "pongal", "ds": "2025-01-14", "lower_window": -1, "upper_window": 0},
    {"holiday": "pongal", "ds": "2026-01-15", "lower_window": -1, "upper_window": 0},
    {"holiday": "onam", "ds": "2024-09-15", "lower_window": -2, "upper_window": 0},
    {"holiday": "onam", "ds": "2025-09-04", "lower_window": -2, "upper_window": 0},
    {"holiday": "onam", "ds": "2026-09-23", "lower_window": -2, "upper_window": 0},
    {"holiday": "republic_day", "ds": "2024-01-26", "lower_window": 0, "upper_window": 0},
    {"holiday": "republic_day", "ds": "2025-01-26", "lower_window": 0, "upper_window": 0},
    {"holiday": "republic_day", "ds": "2026-01-26", "lower_window": 0, "upper_window": 0},
    {"holiday": "independence_day", "ds": "2024-08-15", "lower_window": 0, "upper_window": 0},
    {"holiday": "independence_day", "ds": "2025-08-15", "lower_window": 0, "upper_window": 0},
    {"holiday": "independence_day", "ds": "2026-08-15", "lower_window": 0, "upper_window": 0},
    {"holiday": "navratri_start", "ds": "2024-10-03", "lower_window": 0, "upper_window": 9},
    {"holiday": "dussehra", "ds": "2024-10-12", "lower_window": 0, "upper_window": 0},
    {"holiday": "navratri_start", "ds": "2025-09-22", "lower_window": 0, "upper_window": 9},
    {"holiday": "dussehra", "ds": "2025-10-01", "lower_window": 0, "upper_window": 0},
    {"holiday": "navratri_start", "ds": "2026-10-12", "lower_window": 0, "upper_window": 9},
    {"holiday": "dussehra", "ds": "2026-10-20", "lower_window": 0, "upper_window": 0},
    {"holiday": "christmas", "ds": "2024-12-25", "lower_window": -1, "upper_window": 1},
    {"holiday": "christmas", "ds": "2025-12-25", "lower_window": -1, "upper_window": 1},
    {"holiday": "christmas", "ds": "2026-12-25", "lower_window": -1, "upper_window": 1},
    {"holiday": "new_year", "ds": "2025-01-01", "lower_window": -1, "upper_window": 0},
    {"holiday": "new_year", "ds": "2026-01-01", "lower_window": -1, "upper_window": 0},
]

INDIAN_HOLIDAYS_DF = pd.DataFrame(FESTIVAL_DATES)
INDIAN_HOLIDAYS_DF["ds"] = pd.to_datetime(INDIAN_HOLIDAYS_DF["ds"])


def get_next_festival(today: date) -> dict | None:
    today_ts = pd.Timestamp(today)
    upcoming = INDIAN_HOLIDAYS_DF[INDIAN_HOLIDAYS_DF["ds"] > today_ts].sort_values("ds")
    if upcoming.empty:
        return None
    next_row = upcoming.iloc[0]
    days_away = (next_row["ds"].date() - today).days
    return {
        "name": next_row["holiday"].replace("_", " ").title(),
        "date": next_row["ds"].date().isoformat(),
        "days_away": days_away,
        "expected_uplift_pct": 40 if "diwali" in next_row["holiday"] else 25,
    }


def get_upcoming_festivals(days_ahead: int = 60) -> list:
    today = pd.Timestamp.now()
    end_date = today + pd.Timedelta(days=days_ahead)
    upcoming = INDIAN_HOLIDAYS_DF[
        (INDIAN_HOLIDAYS_DF["ds"] > today) & (INDIAN_HOLIDAYS_DF["ds"] <= end_date)
    ].sort_values("ds")
    
    return [
        {
            "name": row["holiday"].replace("_", " ").title(),
            "date": row["ds"].date().isoformat(),
            "expected_uplift_pct": 40 if "diwali" in row["holiday"] else 25,
        }
        for _, row in upcoming.iterrows()
    ]
