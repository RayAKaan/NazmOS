import pandas as pd
from datetime import date

# Saudi Arabia retail-relevant holidays 2024-2027
# Ramadan / Eid dates are Hijri-based – approximate Gregorian for Prophet
FESTIVAL_DATES = [
    # Ramadan – huge retail spike, especially last 10 days
    {"holiday": "ramadan_start", "ds": "2024-03-11", "lower_window": 0, "upper_window": 29},
    {"holiday": "ramadan_peak", "ds": "2024-03-31", "lower_window": -10, "upper_window": 0},
    {"holiday": "ramadan_start", "ds": "2025-03-01", "lower_window": 0, "upper_window": 29},
    {"holiday": "ramadan_peak", "ds": "2025-03-21", "lower_window": -10, "upper_window": 0},
    {"holiday": "ramadan_start", "ds": "2026-02-18", "lower_window": 0, "upper_window": 29},
    {"holiday": "ramadan_peak", "ds": "2026-03-10", "lower_window": -10, "upper_window": 0},
    {"holiday": "ramadan_start", "ds": "2027-02-08", "lower_window": 0, "upper_window": 29},
    {"holiday": "ramadan_peak", "ds": "2027-02-28", "lower_window": -10, "upper_window": 0},
    
    # Eid al-Fitr
    {"holiday": "eid_al_fitr", "ds": "2024-04-10", "lower_window": -3, "upper_window": 3},
    {"holiday": "eid_al_fitr", "ds": "2025-03-31", "lower_window": -3, "upper_window": 3},
    {"holiday": "eid_al_fitr", "ds": "2026-03-20", "lower_window": -3, "upper_window": 3},
    {"holiday": "eid_al_fitr", "ds": "2027-03-09", "lower_window": -3, "upper_window": 3},
    
    # Hajj / Eid al-Adha
    {"holiday": "hajj_season", "ds": "2024-06-14", "lower_window": -5, "upper_window": 5},
    {"holiday": "eid_al_adha", "ds": "2024-06-16", "lower_window": -2, "upper_window": 3},
    {"holiday": "hajj_season", "ds": "2025-06-04", "lower_window": -5, "upper_window": 5},
    {"holiday": "eid_al_adha", "ds": "2025-06-06", "lower_window": -2, "upper_window": 3},
    {"holiday": "hajj_season", "ds": "2026-05-24", "lower_window": -5, "upper_window": 5},
    {"holiday": "eid_al_adha", "ds": "2026-05-26", "lower_window": -2, "upper_window": 3},
    
    # Saudi National Day – Sept 23
    {"holiday": "saudi_national_day", "ds": "2024-09-23", "lower_window": -2, "upper_window": 1},
    {"holiday": "saudi_national_day", "ds": "2025-09-23", "lower_window": -2, "upper_window": 1},
    {"holiday": "saudi_national_day", "ds": "2026-09-23", "lower_window": -2, "upper_window": 1},
    {"holiday": "saudi_national_day", "ds": "2027-09-23", "lower_window": -2, "upper_window": 1},
    
    # Saudi Founding Day – Feb 22
    {"holiday": "founding_day", "ds": "2025-02-22", "lower_window": -1, "upper_window": 1},
    {"holiday": "founding_day", "ds": "2026-02-22", "lower_window": -1, "upper_window": 1},
    {"holiday": "founding_day", "ds": "2027-02-22", "lower_window": -1, "upper_window": 1},
    
    # White Friday / Singles Day – Nov
    {"holiday": "white_friday", "ds": "2024-11-29", "lower_window": -3, "upper_window": 1},
    {"holiday": "white_friday", "ds": "2025-11-28", "lower_window": -3, "upper_window": 1},
    {"holiday": "white_friday", "ds": "2026-11-27", "lower_window": -3, "upper_window": 1},
    
    # Back to School – late Aug
    {"holiday": "back_to_school", "ds": "2024-08-18", "lower_window": -7, "upper_window": 7},
    {"holiday": "back_to_school", "ds": "2025-08-24", "lower_window": -7, "upper_window": 7},
    {"holiday": "back_to_school", "ds": "2026-08-23", "lower_window": -7, "upper_window": 7},
]

SAUDI_HOLIDAYS_DF = pd.DataFrame(FESTIVAL_DATES)
SAUDI_HOLIDAYS_DF["ds"] = pd.to_datetime(SAUDI_HOLIDAYS_DF["ds"])

# Backward compatibility – Prophet service imports INDIAN_HOLIDAYS_DF
INDIAN_HOLIDAYS_DF = SAUDI_HOLIDAYS_DF

def get_next_festival(today: date) -> dict | None:
    today_ts = pd.Timestamp(today)
    upcoming = SAUDI_HOLIDAYS_DF[SAUDI_HOLIDAYS_DF["ds"] > today_ts].sort_values("ds")
    if upcoming.empty:
        return None
    next_row = upcoming.iloc[0]
    days_away = (next_row["ds"].date() - today).days
    name = next_row["holiday"].replace("_", " ").title()
    # uplift estimates for Saudi retail
    if "ramadan" in next_row["holiday"]:
        uplift = 85
    elif "eid" in next_row["holiday"]:
        uplift = 60
    elif "hajj" in next_row["holiday"]:
        uplift = 35
    elif "white_friday" in next_row["holiday"]:
        uplift = 45
    else:
        uplift = 25
    return {
        "name": name,
        "date": next_row["ds"].date().isoformat(),
        "days_away": days_away,
        "expected_uplift_pct": uplift,
    }


def get_upcoming_festivals(days_ahead: int = 60) -> list:
    today = pd.Timestamp.now()
    end_date = today + pd.Timedelta(days=days_ahead)
    upcoming = SAUDI_HOLIDAYS_DF[
        (SAUDI_HOLIDAYS_DF["ds"] > today) & (SAUDI_HOLIDAYS_DF["ds"] <= end_date)
    ].sort_values("ds")
    
    def uplift_for(name: str) -> int:
        n = name.lower()
        if "ramadan" in n: return 85
        if "eid" in n: return 60
        if "hajj" in n: return 35
        if "white_friday" in n: return 45
        return 25
    
    return [
        {
            "name": row["holiday"].replace("_", " ").title(),
            "date": row["ds"].date().isoformat(),
            "expected_uplift_pct": uplift_for(row["holiday"]),
        }
        for _, row in upcoming.iterrows()
    ]
