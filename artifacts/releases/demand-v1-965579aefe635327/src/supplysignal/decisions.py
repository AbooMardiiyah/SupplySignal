"""Verification-first decisions from monthly reports and officer observations.

The queue has no calibrated stockout probability. Unverified reports can only
produce investigation tasks; transfer proposals need fresh counts at both ends.
"""

from __future__ import annotations

import csv
import json
import logging
import math
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from .reporting import latest_due_month


logger = logging.getLogger("supplysignal.decisions")


ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
AS_OF = date(2026, 10, 4)
MAX_DONOR_DISTANCE_KM = 75.0
PRIORITY_POLICIES = ("absolute_gap", "coverage_gap", "zero_stock_first", "receipt_gap")
DEFAULT_PRIORITY_POLICY = "absolute_gap"


def transferable_units(stock: int, monthly_demand: int) -> int:
    """Reserve one month of expected use plus one month of safety stock."""
    return max(0, stock - 2 * monthly_demand)


def _read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _distance_km(a: dict, b: dict) -> float:
    lat1, lon1 = math.radians(float(a["latitude"])), math.radians(float(a["longitude"]))
    lat2, lon2 = math.radians(float(b["latitude"])), math.radians(float(b["longitude"]))
    return 6371.0 * 2 * math.asin(
        math.sqrt(
            math.sin((lat2 - lat1) / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
        )
    )


def _investigation_score(info: dict, month_index: int, policy: str) -> float:
    """Rank calls, never interpret this number as a stockout probability."""
    if policy not in PRIORITY_POLICIES:
        raise ValueError(f"Unknown priority policy: {policy}")
    if info["stock"] is None or info["forecast"] is None:
        return 10.0 if policy == "absolute_gap" else 1.0
    last_index = int(info["last_period"][:4]) * 12 + int(info["last_period"][5:7]) - 1
    age = max(1, month_index - last_index)
    forecast = max(1, info["forecast"])
    gap_units = max(0, age * forecast - info["stock"])
    gap_months = max(0.0, age - info["stock"] / forecast)
    if policy == "absolute_gap":
        return float(gap_units)
    if policy == "receipt_gap":
        # A gap with no recent recorded replenishment is more worth checking.
        # This remains an investigation heuristic: an unreported delivery may exist.
        return float(gap_units * (1 + info["zero_receipt_reports_last_2"])
                     + (100 if info["last_stockout_days"] else 0))
    if policy == "coverage_gap":
        return round(gap_months, 4)
    return round((100.0 if info["stock"] == 0 else 0.0) + gap_months, 4)


def _signal_and_step(info: dict, action: str) -> tuple[str, str]:
    """Explain the evidence behind a work item without implying certainty."""
    if action == "no_action":
        return "No immediate signal", "Review at the next reporting cycle."
    if action == "propose_transfer_for_verification":
        return "Counted shortage", "Check expiry, route and approval before any transfer."
    if action == "verify_donor":
        return "Counted shortage", "Count the proposed donor's stock before considering transfer."
    if action == "escalate_resupply":
        return "Counted shortage", "Contact the LGA supply lead for resupply; check incoming deliveries."
    if info["stock"] == 0:
        return "Zero in last report", "Call the facility; confirm stock and deliveries since the report."
    if info["last_stockout_days"] and info["last_stockout_days"] > 0:
        return "Recent reported stockout", "Call the facility; confirm whether the product is available now."
    if info["status"] == "no_reports":
        return "No submitted report", "Contact the facility and obtain a physical stock count."
    if info["status"] in {"stale", "verification_expired"}:
        return "Late or expired evidence", "Request a fresh count and check for unreported deliveries."
    if info["stock"] is not None and info["forecast"] and info["stock"] <= info["forecast"]:
        return "Low reported cover", "Confirm current stock before requesting more supply."
    return "Forecast-only gap", "Check stock and receipts; this is not a confirmed shortage."


def facility_call_plan(queue: list[dict], capacity: int | None = None) -> list[dict]:
    """Turn ranked product investigations into unique facility calls.

    The first occurrence sets call order; all flagged products at that facility
    are included so a second commodity does not consume another call slot.
    """
    if capacity is not None and capacity <= 0:
        raise ValueError("Call capacity must be positive")
    calls: dict[str, dict] = {}
    for case in queue:
        if case["action"] == "no_action":
            continue
        facility_id = case["facility_id"]
        if facility_id not in calls:
            calls[facility_id] = {
                "facility_id": facility_id,
                "facility_name": case["facility_name"],
                "lead_action": case["action"],
                "lead_signal": case["signal"],
                "products": [],
                "case_count": 0,
            }
        calls[facility_id]["products"].append(case["commodity_name"])
        calls[facility_id]["case_count"] += 1
    result = list(calls.values())
    return result[:capacity] if capacity is not None else result


def create_queue(
    as_of: date = AS_OF, events: list[dict] | None = None, include_clear: bool = False,
    priority_policy: str = DEFAULT_PRIORITY_POLICY, forecast_strategy: str = "model",
    ledger_path: Path | None = None, facilities_path: Path | None = None,
) -> list[dict]:
    if priority_policy not in PRIORITY_POLICIES:
        raise ValueError(f"Unknown priority policy: {priority_policy}")
    if forecast_strategy not in {"model", "three_report_mean"}:
        raise ValueError(f"Unknown forecast strategy: {forecast_strategy}")
    ledger_path = ledger_path or PROCESSED / "synthetic_lmis.csv"
    facilities_path = facilities_path or PROCESSED / "facilities.csv"
    facilities = {r["facility_id"]: r for r in _read(facilities_path)}
    grouped = defaultdict(list)
    for row in _read(ledger_path):
        if date.fromisoformat(row["period"]) > as_of:
            continue
        grouped[(row["facility_id"], row["commodity_id"])].append(row)
    model_forecasts = {}
    model_name = "three_report_mean"
    artifact_path = ROOT / "artifacts" / "demand_model.joblib"
    if forecast_strategy == "model" and artifact_path.exists():
        from .inference import predict

        current_month = date(as_of.year, as_of.month, 1).isoformat()
        forecast_frame = predict(ledger_path, artifact_path, current_month, as_of.isoformat())
        model_forecasts = {
            (row.facility_id, row.commodity_id): float(row.forecast_demand_units)
            for row in forecast_frame.itertuples()
        }
        model_name = str(forecast_frame["model_name"].iloc[0])
    elif forecast_strategy == "model":
        logger.warning("model_artifact_missing_using_report_mean")
    # The same day-10 assumption is used in the import preview.
    month_index = as_of.year * 12 + as_of.month - 1
    latest_due_period = latest_due_month(as_of)
    previous_index = month_index - 1
    previous_period = date(previous_index // 12, previous_index % 12 + 1, 1)
    state = {}
    for key, rows in grouped.items():
        rows.sort(key=lambda r: r["period"])
        visible = [
            r for r in rows
            if r["report_status"] == "reported"
            and r["submitted_at"]
            and date.fromisoformat(r["submitted_at"]) <= as_of
        ]
        if not visible:
            state[key] = {
                "status": "no_reports", "forecast": max(1, math.ceil(model_forecasts[key])) if key in model_forecasts else None,
                "stock": None, "reported_stock": None, "commodity_name": rows[0]["commodity_name"],
                "last_period": "", "last_submitted": "", "verified_date": None,
                "expected_receipts": [], "event_count": 0, "last_stockout_days": None,
                "zero_receipt_reports_last_2": 0,
            }
            continue
        latest = visible[-1]
        recent = visible[-3:]
        baseline = max(1, math.ceil(sum(int(r["consumption"]) for r in recent) / len(recent)))
        forecast = max(1, math.ceil(model_forecasts.get(key, baseline)))
        state[key] = {
            "status": "current" if latest["period"] >= latest_due_period.isoformat() else "stale",
            "forecast": forecast,
            "stock": int(latest["closing_stock"]),
            "reported_stock": int(latest["closing_stock"]),
            "last_period": latest["period"],
            "last_submitted": latest["submitted_at"],
            "commodity_name": latest["commodity_name"],
            "verified_date": None,
            "expected_receipts": [],
            "event_count": 0,
            "last_stockout_days": int(latest["stockout_days"]) if latest.get("stockout_days") else 0,
            "zero_receipt_reports_last_2": sum(int(r["receipts"]) == 0 for r in visible[-2:]),
        }

    for event in events or []:
        key = (event["facility_id"], event["commodity_id"])
        if key not in state or date.fromisoformat(event["event_date"]) > as_of:
            continue
        info = state[key]
        info["event_count"] += 1
        if event["event_type"] == "stock_count":
            # A physical count supersedes every earlier report or receipt.
            info["stock"] = int(event["units"])
            info["verified_date"] = date.fromisoformat(event["event_date"])
        elif event["event_type"] == "receipt_confirmed":
            if info["stock"] is not None:
                info["stock"] += int(event["units"])
        elif event["event_type"] == "receipt_expected":
            info["expected_receipts"].append(event)

    for info in state.values():
        if info["verified_date"] is not None:
            info["status"] = "verified" if as_of - info["verified_date"] <= timedelta(days=7) else "verification_expired"

    queue = []
    # Holds apply to this proposed plan only, not to physical stock. Allocate
    # deterministically, largest confirmed gap first within each commodity.
    # No proposed transfer can become another proposal's incoming stock.
    reserved = defaultdict(int)
    ordered = sorted(state.items(), key=lambda item: (
        item[0][1],
        -max(0, (item[1]["forecast"] or 0) - (item[1]["stock"] or 0))
        if item[1]["status"] == "verified" else 0,
        item[0][0],
    ))
    for (facility_id, commodity_id), info in ordered:
        facility = facilities[facility_id]
        record = {
            "facility_id": facility_id,
            "facility_name": facility["facility_name"],
            "commodity_id": commodity_id,
            "commodity_name": info.get("commodity_name", commodity_id),
            "as_of": as_of.isoformat(),
            "last_report_period": info.get("last_period", ""),
            "stock_on_last_report": info["reported_stock"] if info["reported_stock"] is not None else "",
            "effective_stock": info["stock"] if info["stock"] is not None else "",
            "four_week_demand_baseline": info["forecast"] if info["forecast"] is not None else "",
            "forecast_method": model_name,
            "evidence_status": info["status"],
            "last_verified_at": info["verified_date"].isoformat() if info["verified_date"] else "",
            "expected_receipt_units": sum(int(event["units"]) for event in info["expected_receipts"]),
            "next_expected_arrival": min((event["expected_date"] for event in info["expected_receipts"]), default=""),
            "observation_count": info["event_count"],
            "last_stockout_days": info["last_stockout_days"] if info["last_stockout_days"] is not None else "",
            "zero_receipt_reports_last_2": info["zero_receipt_reports_last_2"],
            "stock_coverage_months": round(info["stock"] / info["forecast"], 2)
            if info["stock"] is not None and info["forecast"] else "",
            "action": "",
            "reason": "",
            "suggested_units": "",
            "remaining_shortage_units": "",
            "donor_facility_id": "",
            "donor_facility_name": "",
            "donor_distance_km": "",
            "priority_score": 0,
            "data_provenance": "real facility; simulated inventory",
        }
        if info["status"] != "verified":
            score = _investigation_score(info, month_index, priority_policy)
            gap = _investigation_score(info, month_index, "absolute_gap")
            if info["stock"] is None:
                gap = 0
            due_missing = info["status"] in {"stale", "no_reports", "verification_expired"}
            if due_missing or gap > 0:
                record["action"] = "verify_stock"
                record["reason"] = (
                    "No usable current count; confirm physical stock and any deliveries before acting"
                    if due_missing else
                    "Reported balance may not cover the next four weeks; confirm physical stock and deliveries"
                )
                record["priority_score"] = score
                queue.append(record)
            elif include_clear:
                record["action"] = "no_action"
                record["reason"] = "No immediate investigation signal from available reports"
                queue.append(record)
            if record["action"]:
                record["signal"], record["next_step"] = _signal_and_step(info, record["action"])
            continue
        shortage_units = max(0, info["forecast"] - info["stock"]) if info["forecast"] is not None else 0
        if shortage_units == 0:
            if include_clear:
                record["action"] = "no_action"
                record["reason"] = "Verified stock covers the four-week forecast"
                record["signal"], record["next_step"] = _signal_and_step(info, record["action"])
                queue.append(record)
            continue
        record["priority_score"] = shortage_units
        candidates = []
        for (candidate_id, candidate_commodity), donor in state.items():
            if candidate_id == facility_id or candidate_commodity != commodity_id:
                continue
            if donor["stock"] is None or donor["forecast"] is None:
                continue
            if donor["status"] != "verified" and donor["last_period"] < previous_period.isoformat():
                continue
            # Preserve one forecast month of demand and one safety month.
            transferable = max(0, transferable_units(donor["stock"], donor["forecast"])
                               - reserved[(candidate_id, candidate_commodity)])
            if transferable <= 0:
                continue
            distance = _distance_km(facility, facilities[candidate_id])
            if distance <= MAX_DONOR_DISTANCE_KM:
                candidates.append((donor["status"] != "verified", distance, -transferable, candidate_id, transferable))
        candidates.sort()
        if candidates and candidates[0][0] is False:
            _, distance, _, donor_id, transferable = candidates[0]
            record["action"] = "propose_transfer_for_verification"
            record["reason"] = "Both physical counts are fresh; proposed donor retains forecast demand and safety stock. Check expiry, route and approval"
            record["suggested_units"] = min(shortage_units, transferable)
            reserved[(donor_id, commodity_id)] += record["suggested_units"]
            record["remaining_shortage_units"] = shortage_units - record["suggested_units"]
            if record["remaining_shortage_units"]:
                record["reason"] += "; partial proposal: escalate the remaining shortage"
            record["donor_facility_id"] = donor_id
            record["donor_facility_name"] = facilities[donor_id]["facility_name"]
            record["donor_distance_km"] = round(distance, 1)
        elif candidates:
            _, distance, _, donor_id, _ = candidates[0]
            record["action"] = "verify_donor"
            record["reason"] = "Recipient shortage is verified; a nearby reported donor needs a physical count before transfer can be proposed"
            record["donor_facility_id"] = donor_id
            record["donor_facility_name"] = facilities[donor_id]["facility_name"]
            record["donor_distance_km"] = round(distance, 1)
        else:
            record["action"] = "escalate_resupply"
            record["reason"] = "Verified stock is below four-week forecast; no unallocated, safely transferable local donor in current records"
            record["suggested_units"] = shortage_units
        record["signal"], record["next_step"] = _signal_and_step(info, record["action"])
        if record["remaining_shortage_units"]:
            record["next_step"] += f" Escalate the remaining {record['remaining_shortage_units']} units."
        queue.append(record)
    priority = {"escalate_resupply": 0, "propose_transfer_for_verification": 1, "verify_donor": 2, "verify_stock": 3, "no_action": 4}
    queue.sort(key=lambda r: (priority[r["action"]], -r["priority_score"], r["facility_name"], r["commodity_id"]))
    logger.debug("queue_created", extra={"context": {"cases": len(queue), "as_of": as_of}})
    return queue


def main() -> None:
    queue = create_queue()
    path = PROCESSED / "action_queue.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(queue[0]))
        writer.writeheader()
        writer.writerows(queue)
    counts = defaultdict(int)
    for row in queue:
        counts[row["action"]] += 1
    print(json.dumps({"as_of": AS_OF.isoformat(), "alerts": len(queue), "actions": dict(counts)}, indent=2))


if __name__ == "__main__":
    from .logging_config import run_cli

    run_cli(main)
