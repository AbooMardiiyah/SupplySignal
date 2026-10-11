"""Conservative, model-free triage for an uploaded monthly LMIS extract.

This preview does not use the model trained on synthetic reports. Every output
is a request to verify or reconcile, never an instruction to move stock.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from .reporting import REPORT_DUE_DAY, latest_due_month


def expected_report_period(as_of: date, due_day: int = REPORT_DUE_DAY) -> pd.Period:
    """Previous month is due on day 10; before then, the month before it is due."""
    return pd.Period(latest_due_month(as_of, due_day), freq="M")


def preview_worklist(reports: pd.DataFrame, roster: pd.DataFrame, as_of: date) -> pd.DataFrame:
    """Create one auditable verification case for each expected pair needing work."""
    required = {"facility_id", "commodity_id", "period", "submitted_at", "closing_stock", "consumption"}
    missing = required - set(reports)
    if missing:
        raise ValueError(f"Normalized report is missing columns: {sorted(missing)}")
    if not {"facility_id", "commodity_id"}.issubset(roster.columns):
        raise ValueError("Roster needs facility_id and commodity_id")
    pairs = roster[["facility_id", "commodity_id"]].copy()
    if pairs.empty:
        raise ValueError("Roster contains no facility-product pairs")
    if pairs.isna().any().any() or pairs.eq("").any().any():
        raise ValueError("Roster identifiers cannot be blank")
    if pairs.duplicated().any():
        raise ValueError("Roster has duplicate facility-product pairs")
    visible = reports.copy()
    visible["period"] = pd.to_datetime(visible["period"], errors="raise")
    visible["submitted_at"] = pd.to_datetime(visible["submitted_at"], errors="raise")
    visible = visible[
        (visible["submitted_at"].dt.date <= as_of)
        & (visible["period"].dt.to_period("M") <= pd.Period(as_of, freq="M"))
    ]
    if visible.duplicated(["facility_id", "commodity_id", "period"]).any():
        raise ValueError("Visible reports contain duplicate facility-product-month keys")
    expected = expected_report_period(as_of)
    cases = []
    for item in pairs.itertuples(index=False):
        pair_reports = visible[
            (visible["facility_id"] == item.facility_id)
            & (visible["commodity_id"] == item.commodity_id)
        ].sort_values(["period", "submitted_at"])
        latest = pair_reports.iloc[-1] if not pair_reports.empty else None
        if latest is None:
            signal = "Never reported"
            action = "Verify reporting and stock"
            detail = "No submitted report is visible for this expected facility-product pair."
            last_period = ""
            stock = None
            demand = None
        else:
            last_period = latest["period"].strftime("%Y-%m")
            stock = float(latest["closing_stock"])
            uncensored = pair_reports.tail(3)
            if "stockout_days" in uncensored:
                uncensored = uncensored[uncensored["stockout_days"].fillna(1).eq(0)]
            demand = float(uncensored["consumption"].mean()) if len(uncensored) >= 2 else None
            if latest["period"].to_period("M") < expected:
                signal = "Late or missing expected report"
                action = "Verify reporting and stock"
                detail = f"Last visible report is {last_period}; {expected} is due under the day-10 assumption."
            elif "balance_discrepancy" in latest and pd.notna(latest["balance_discrepancy"]) and latest["balance_discrepancy"] != 0:
                signal = "Unreconciled stock balance"
                action = "Reconcile report and count stock"
                detail = "Closing count differs from opening + receipts - consumption - losses + adjustments."
            elif stock == 0:
                signal = "Zero in last report"
                action = "Verify physical stock"
                detail = "Last submitted report says zero; current stock is unconfirmed."
            elif "stockout_days" in latest and pd.notna(latest["stockout_days"]) and latest["stockout_days"] > 0:
                signal = "Reported stockout days"
                action = "Verify physical stock"
                detail = "Last submitted report records days without stock; current stock is unconfirmed."
            elif demand is not None and stock <= demand:
                signal = "Low reported cover"
                action = "Verify physical stock"
                detail = "Last submitted balance covers at most one month of recent uncensored consumption."
            else:
                signal = "No direct warning"
                action = "No immediate check"
                detail = "No direct warning in visible reports; this is not proof of adequate stock."
        cases.append({
            "facility_id": item.facility_id,
            "commodity_id": item.commodity_id,
            "signal": signal,
            "action": action,
            "last_report_period": last_period,
            "last_reported_stock": stock,
            "monthly_consumption_baseline": demand,
            "why": detail,
        })
    frame = pd.DataFrame(cases)
    order = {
        "Never reported": 0,
        "Late or missing expected report": 1,
        "Unreconciled stock balance": 2,
        "Zero in last report": 3,
        "Reported stockout days": 4,
        "Low reported cover": 5,
        "No direct warning": 6,
    }
    frame["_order"] = frame["signal"].map(order)
    return frame.sort_values(["_order", "facility_id", "commodity_id"]).drop(columns="_order").reset_index(drop=True)
