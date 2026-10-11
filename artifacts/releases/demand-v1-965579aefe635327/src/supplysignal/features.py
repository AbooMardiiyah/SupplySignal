"""Point-in-time features shared by model training and live inference."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


NUMERIC_FEATURES = (
    "month_sin",
    "month_cos",
    "last_consumption",
    "mean_3_consumption",
    "mean_6_consumption",
    "std_3_consumption",
    "report_age_months",
    "visible_reports_last_3",
    "visible_reports_last_6",
)
META_COLUMNS = (
    "facility_id", "commodity_id", "target_period", "as_of", "label_consumption",
    "label_observed", "label_uncensored", "label_submitted_at", "truth_demand", "truth_stockout",
)


@dataclass(frozen=True)
class Split:
    train_end: str = "2026-02-01"
    validation_end: str = "2026-05-01"
    test_end: str = "2026-09-01"


def prepare_ledger(frame: pd.DataFrame) -> pd.DataFrame:
    needed = {"facility_id", "commodity_id", "period", "consumption", "closing_stock", "submitted_at", "report_status"}
    missing = needed - set(frame)
    if missing:
        raise ValueError(f"Ledger is missing required fields: {sorted(missing)}")
    result = frame.copy()
    result["period"] = pd.to_datetime(result["period"])
    result["submitted_at"] = pd.to_datetime(result["submitted_at"])
    for name in ("consumption", "closing_stock", "stockout_days", "truth_latent_demand", "truth_unmet_units"):
        if name in result:
            result[name] = pd.to_numeric(result[name], errors="coerce")
    if result.duplicated(["facility_id", "commodity_id", "period"]).any():
        raise ValueError("Duplicate facility × commodity × period records")
    return result.sort_values(["facility_id", "commodity_id", "period"])


def _month_index(timestamp: pd.Timestamp) -> int:
    return timestamp.year * 12 + timestamp.month - 1


def snapshot_features(
    ledger: pd.DataFrame,
    target_period: str | pd.Timestamp,
    as_of: str | pd.Timestamp | None = None,
    expected_pairs: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build one feature row per series using reports visible before target month.

    `truth_*` appears only as an evaluation label. It never enters the model
    feature matrix or inference path.
    """
    target = pd.Timestamp(target_period).to_period("M").to_timestamp()
    cutoff = pd.Timestamp(as_of) if as_of is not None else target
    history = ledger[
        (ledger["period"] < target)
        & (ledger["submitted_at"] <= cutoff)
        & (ledger["report_status"] == "reported")
    ]
    target_rows = ledger[ledger["period"] == target].set_index(["facility_id", "commodity_id"])
    pairs = expected_pairs if expected_pairs is not None else ledger
    series_keys = pairs[["facility_id", "commodity_id"]].drop_duplicates().itertuples(index=False, name=None)
    rows = []
    target_index = _month_index(target)
    for facility_id, commodity_id in series_keys:
        visible = history[
            (history["facility_id"] == facility_id)
            & (history["commodity_id"] == commodity_id)
        ].sort_values("period")
        last = visible.iloc[-1] if len(visible) else None
        consumption = visible["consumption"].dropna()
        recent3 = consumption.iloc[-3:]
        recent6 = consumption.iloc[-6:]
        age = target_index - _month_index(last["period"]) if last is not None else np.nan
        stock = float(last["closing_stock"]) if last is not None else np.nan
        mean3 = float(recent3.mean()) if len(recent3) else np.nan
        expected3 = {target_index - i for i in range(1, 4)}
        expected6 = {target_index - i for i in range(1, 7)}
        visible_indexes = {_month_index(period) for period in visible["period"]}
        label = target_rows.loc[(facility_id, commodity_id)] if (facility_id, commodity_id) in target_rows.index else None
        label_observed = bool(label is not None and label["report_status"] == "reported")
        days = label.get("stockout_days", np.nan) if label is not None else np.nan
        label_uncensored = bool(label_observed and pd.notna(days) and days == 0 and label["closing_stock"] > 0)
        rows.append(
            {
                "facility_id": facility_id,
                "commodity_id": commodity_id,
                "target_period": target,
                "as_of": cutoff,
                "label_consumption": float(label["consumption"]) if label_observed else np.nan,
                "label_observed": label_observed,
                "label_uncensored": label_uncensored,
                "label_submitted_at": label["submitted_at"] if label_observed else pd.NaT,
                "truth_demand": float(label["truth_latent_demand"]) if label is not None and "truth_latent_demand" in label else np.nan,
                "truth_stockout": bool(label["truth_unmet_units"] > 0) if label is not None and "truth_unmet_units" in label else np.nan,
                "month_sin": np.sin(2 * np.pi * target.month / 12),
                "month_cos": np.cos(2 * np.pi * target.month / 12),
                "last_consumption": float(consumption.iloc[-1]) if len(consumption) else np.nan,
                "mean_3_consumption": mean3,
                "mean_6_consumption": float(recent6.mean()) if len(recent6) else np.nan,
                "std_3_consumption": float(recent3.std(ddof=0)) if len(recent3) else np.nan,
                "last_closing_stock": stock,
                "last_stockout_days": float(last["stockout_days"]) if last is not None and "stockout_days" in last and pd.notna(last["stockout_days"]) else np.nan,
                "report_age_months": age,
                "visible_reports_last_3": len(expected3 & visible_indexes),
                "visible_reports_last_6": len(expected6 & visible_indexes),
                "months_of_stock": stock / mean3 if pd.notna(stock) and pd.notna(mean3) and mean3 > 0 else np.nan,
            }
        )
    return pd.DataFrame(rows)


def build_feature_panel(ledger: pd.DataFrame, first_target: str = "2025-04-01") -> pd.DataFrame:
    last_target = ledger["period"].max()
    periods = pd.date_range(first_target, last_target, freq="MS")
    return pd.concat([snapshot_features(ledger, period) for period in periods], ignore_index=True)


def model_matrix(frame: pd.DataFrame, commodity_vocabulary: list[str]) -> pd.DataFrame:
    data = frame[list(NUMERIC_FEATURES)].astype(float).copy()
    for commodity in commodity_vocabulary:
        data[f"commodity__{commodity}"] = (frame["commodity_id"] == commodity).astype(float)
    return data
