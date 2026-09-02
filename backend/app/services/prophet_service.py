import pandas as pd
import numpy as np
from typing import Optional
from datetime import date, timedelta

try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False

from app.config import get_settings
from app.utils.saudi_holidays import SAUDI_HOLIDAYS_DF


class ProphetService:
    def __init__(self, db=None):
        # Optional AsyncSession used by live item-level forecast callers.
        self.db = db
        self._model = None

    def _build_prophet(self) -> "Prophet":
        if not PROPHET_AVAILABLE:
            raise ImportError("Prophet is not installed")
        model = Prophet(
            yearly_seasonality=False,
            weekly_seasonality=False,
            daily_seasonality=False,
            holidays=SAUDI_HOLIDAYS_DF,
        )
        model.add_seasonality(
            name="monthly",
            period=30.5,
            fourier_order=5,
        )
        return model

    def create_model(self, df: pd.DataFrame) -> "Prophet":
        """Fit a Prophet model on the given ``[ds, y]`` dataframe and return it.

        Thin passthrough kept for callers that only need a fitted model
        (e.g. exploratory forecasting and tests).
        """
        if PROPHET_AVAILABLE is False:
            raise ImportError("Prophet is not installed")
        if df.empty:
            raise ValueError("Cannot fit Prophet on an empty dataframe")
        model = self._build_prophet()
        series = df.copy()
        if not series["ds"].is_monotonic_increasing:
            series = series.sort_values("ds")
        model.fit(series)
        self._model = model
        return model

    def make_future_dataframe(self, periods: int) -> pd.DataFrame:
        """Return the future dataframe for a fitted prophet model.

        If no model has been fitted yet on this service instance, a default
        model is fit on a synthetic horizon so standalone use works.
        """
        if not PROPHET_AVAILABLE:
            raise ImportError("Prophet is not installed")
        if self._model is None:
            self._model = self._build_prophet()
            synthetic = pd.DataFrame({
                "ds": pd.date_range("2024-01-01", periods=150),
                "y": 0,
            })
            self._model.fit(synthetic)
        return self._model.make_future_dataframe(periods=periods)

    async def predict_item_demand(self, business_id, item_id, horizon_days: int = 7) -> dict:
        """Return a live item demand forecast using current transaction history.

        Kept intentionally thin so dashboard/detail endpoints can call the same
        Prophet/fallback path without relying on static multipliers only.
        """
        if self.db is None:
            return {"forecast": []}

        from sqlalchemy import text

        res = await self.db.execute(text("""
            SELECT DATE(transaction_at) AS ds, SUM(quantity) AS y
            FROM transactions
            WHERE business_id = :business_id
              AND item_id = :item_id
              AND transaction_at >= NOW() - INTERVAL '180 days'
            GROUP BY DATE(transaction_at)
            ORDER BY ds
        """), {
            "business_id": str(business_id),
            "item_id": str(item_id),
        })
        rows = res.fetchall()
        if not rows:
            return {"forecast": []}

        name_res = await self.db.execute(text("""
            SELECT COALESCE(c.name || ' ', '') || i.name AS item_label
            FROM items i
            LEFT JOIN categories c ON c.id = i.category_id
            WHERE i.business_id = :business_id AND i.id = :item_id
            LIMIT 1
        """), {
            "business_id": str(business_id),
            "item_id": str(item_id),
        })
        item_row = name_res.fetchone()
        item_label = item_row.item_label if item_row else "Item"

        df = pd.DataFrame(rows, columns=["ds", "y"])
        result = self.train_and_forecast(str(item_id), item_label, df, forecast_days=max(7, horizon_days))
        return {"forecast": result.get("forecast_7d", [])[:horizon_days]}

    def train_and_forecast(
        self,
        item_id: str,
        item_name: str,
        transactions_df: pd.DataFrame,
        forecast_days: int = 30,
    ) -> Optional[dict]:
        if not PROPHET_AVAILABLE:
            return self._fallback_forecast(transactions_df, forecast_days, item_name)
        
        if len(transactions_df) < 14:
            return self._fallback_forecast(transactions_df, forecast_days, item_name)

        try:
            daily = (
                transactions_df
                .groupby("ds")["y"]
                .sum()
                .reset_index()
                .sort_values("ds")
            )

            date_range = pd.date_range(daily["ds"].min(), daily["ds"].max())
            daily = (
                daily
                .set_index("ds")
                .reindex(date_range, fill_value=0)
                .reset_index()
                .rename(columns={"index": "ds"})
            )

            if len(daily) < 14:
                return self._fallback_forecast(transactions_df, forecast_days, item_name)

            p97 = daily["y"].quantile(0.97)
            daily["y"] = daily["y"].clip(upper=p97)

            model = Prophet(
                yearly_seasonality=len(daily) > 180,
                weekly_seasonality=True,
                daily_seasonality=False,
                seasonality_mode="multiplicative",
                changepoint_prior_scale=0.05,
                seasonality_prior_scale=10.0,
                holidays=SAUDI_HOLIDAYS_DF,
                interval_width=0.80,
            )

            model.add_seasonality(
                name="monthly",
                period=30.5,
                fourier_order=5,
            )

            model.fit(daily)

            future = model.make_future_dataframe(periods=forecast_days)
            forecast = model.predict(future)

            future_rows = forecast[forecast["ds"] > daily["ds"].max()]

            forecast_7d = [
                {
                    "date": row["ds"].date().isoformat(),
                    "predicted_qty": max(0, round(row["yhat"], 2)),
                    "lower": max(0, round(row["yhat_lower"], 2)),
                    "upper": max(0, round(row["yhat_upper"], 2)),
                }
                for _, row in future_rows.head(7).iterrows()
            ]

            forecast_30d = [
                {
                    "date": row["ds"].date().isoformat(),
                    "predicted_qty": max(0, round(row["yhat"], 2)),
                    "lower": max(0, round(row["yhat_lower"], 2)),
                    "upper": max(0, round(row["yhat_upper"], 2)),
                }
                for _, row in future_rows.head(30).iterrows()
            ]
            forecast_7d = self._maybe_apply_event_uplift(forecast_7d, item_name)
            forecast_30d = self._maybe_apply_event_uplift(forecast_30d, item_name)

            weekday_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            weekly_avgs = daily.groupby(daily["ds"].dt.dayofweek)["y"].mean()
            baseline = weekly_avgs.mean() or 1
            weekly_pattern = {
                weekday_names[i]: round(weekly_avgs.get(i, baseline) / baseline, 3)
                for i in range(7)
            }

            recent = daily.tail(14)["y"].mean()
            prior = daily.iloc[-28:-14]["y"].mean() if len(daily) >= 28 else daily["y"].mean()
            trend_pct = ((recent - prior) / prior * 100) if prior > 0 else 0
            trend_direction = "up" if trend_pct > 8 else "down" if trend_pct < -8 else "stable"

            return {
                "forecast_7d": forecast_7d,
                "forecast_30d": forecast_30d,
                "weekly_pattern": weekly_pattern,
                "trend_direction": trend_direction,
                "trend_strength": round(trend_pct, 2),
                "training_rows": len(daily),
                "mape_score": None,
            }
        except Exception:
            return self._fallback_forecast(transactions_df, forecast_days, item_name)

    def _category_event_multiplier(self, item_name: str, forecast_date: date) -> float:
        """Saudi retail event uplift calibrated by product/category keywords.

        Ramadan examples:
        - Dates: +215% => 3.15x
        - F&B / beverages / coffee: +75% => 1.75x
        """
        text_name = (item_name or "").lower()
        try:
            rows = SAUDI_HOLIDAYS_DF.copy()
            rows["window_start"] = rows["ds"] + pd.to_timedelta(rows["lower_window"], unit="D")
            rows["window_end"] = rows["ds"] + pd.to_timedelta(rows["upper_window"], unit="D")
            ts = pd.Timestamp(forecast_date)
            active = rows[(rows["window_start"] <= ts) & (rows["window_end"] >= ts)]
        except Exception:
            active = pd.DataFrame()

        if active.empty:
            return 1.0

        names = " ".join(str(h).lower() for h in active["holiday"].tolist())
        if "ramadan" in names:
            if any(k in text_name for k in ["date", "dates", "تمر", "تمور", "سكري", "خلاص"]):
                return 3.15
            if any(k in text_name for k in ["food", "f&b", "beverage", "coffee", "milk", "water", "cafe", "restaurant", "مطعم", "قهوة", "حليب", "مياه"]):
                return 1.75
            return 1.35
        if "eid" in names:
            if any(k in text_name for k in ["sweet", "chocolate", "gift", "حلويات", "شوكولاتة", "هدية"]):
                return 1.80
            return 1.40
        return 1.0

    def _maybe_apply_event_uplift(self, forecast_rows: list[dict], item_name: str) -> list[dict]:
        """Apply manual event uplift only when explicitly enabled.

        Prophet already models SAUDI_HOLIDAYS_DF inside the fit; multiplying the
        interval rows afterwards double-counts the holiday effect. Uplift is the
        OM exception, permanently OFF by default (config FORECAST_EVENT_UPLIFT_ENABLED).
        """
        settings = get_settings()
        if not settings.FORECAST_EVENT_UPLIFT_ENABLED:
            return forecast_rows
        return self._apply_event_uplift(forecast_rows, item_name)

    def _apply_event_uplift(self, forecast_rows: list[dict], item_name: str) -> list[dict]:
        adjusted = []
        for row in forecast_rows:
            try:
                d = date.fromisoformat(row["date"])
                mult = self._category_event_multiplier(item_name, d)
                new_row = dict(row)
                if mult != 1.0:
                    new_row["predicted_qty"] = round(float(new_row["predicted_qty"]) * mult, 2)
                    new_row["lower"] = round(float(new_row.get("lower", 0)) * mult, 2)
                    new_row["upper"] = round(float(new_row.get("upper", 0)) * mult, 2)
                    new_row["event_multiplier"] = mult
                adjusted.append(new_row)
            except Exception:
                adjusted.append(row)
        return adjusted

    def _fallback_forecast(self, transactions_df: pd.DataFrame, forecast_days: int, item_name: str = "") -> dict:
        if len(transactions_df) == 0:
            return {
                "forecast_7d": [{"date": (date.today() + timedelta(days=i)).isoformat(),
                               "predicted_qty": 0, "lower": 0, "upper": 0} for i in range(1, 8)],
                "forecast_30d": [{"date": (date.today() + timedelta(days=i)).isoformat(),
                                "predicted_qty": 0, "lower": 0, "upper": 0} for i in range(1, 31)],
                "weekly_pattern": {
                    "monday": 0.90, "tuesday": 0.70, "wednesday": 0.88,
                    "thursday": 1.38, "friday": 1.45, "saturday": 1.30, "sunday": 0.85
                },
                "trend_direction": "stable",
                "trend_strength": 0,
                "training_rows": 0,
                "mape_score": None,
            }

        daily_avg = transactions_df["y"].mean()
        
        forecast_7d = []
        forecast_30d = []
        for i in range(1, 31):
            forecast_date = date.today() + timedelta(days=i)
            dow = forecast_date.weekday()
            
            # KSA retail weekly multipliers (3=Thu, 4=Fri, 5=Sat weekend rush; 1=Tue mid-week lull)
            multipliers = {3: 1.38, 4: 1.45, 5: 1.30, 6: 0.85, 1: 0.70}
            multiplier = multipliers.get(dow, 1.0)
            predicted = max(0, daily_avg * multiplier)
            
            entry = {
                "date": forecast_date.isoformat(),
                "predicted_qty": round(predicted, 2),
                "lower": round(max(0, predicted * 0.7), 2),
                "upper": round(predicted * 1.3, 2),
            }
            
            if i <= 7:
                forecast_7d.append(entry)
            forecast_30d.append(entry)

        forecast_7d = self._maybe_apply_event_uplift(forecast_7d, item_name)
        forecast_30d = self._maybe_apply_event_uplift(forecast_30d, item_name)

        return {
            "forecast_7d": forecast_7d,
            "forecast_30d": forecast_30d,
            "weekly_pattern": {
                "monday": 0.90, "tuesday": 0.70, "wednesday": 0.88,
                "thursday": 1.38, "friday": 1.45, "saturday": 1.30, "sunday": 0.85
            },
            "trend_direction": "stable",
            "trend_strength": 0,
            "training_rows": len(transactions_df),
            "mape_score": None,
        }
