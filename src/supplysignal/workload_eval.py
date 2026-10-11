"""Compare ten-facility-call worklists on the same point-in-time candidates.

All outcomes here come from the simulator's hidden truth, never from a real PHC.
Every policy uses the same ten-call budget and checks all flagged products at
each called facility. A shortage in an unflagged product is a miss, not a hit.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from .decisions import create_queue, facility_call_plan
from .ranking_eval import DEVELOPMENT, EXPLORED_TEST, VALIDATION
from .train import DEFAULT_LEDGER


DEFAULT_REPORT = Path(__file__).resolve().parents[2] / "data/processed/workload_report.json"
POLICIES = ("SupplySignal gap", "Reported-zero first", "Oldest-report first")
GROUPS = {
    "development_mean_already_inspected": (DEVELOPMENT, "three_report_mean"),
    "validation_mean_already_inspected": (VALIDATION, "three_report_mean"),
    "later_mean_already_inspected": (EXPLORED_TEST, "three_report_mean"),
    "later_model_already_inspected": (EXPLORED_TEST, "model"),
}


def order_cases(cases: list[dict], policy: str) -> list[dict]:
    """Order the same candidate cases using only decision-time visible fields."""
    if policy not in POLICIES:
        raise ValueError(f"Unknown worklist policy: {policy}")
    if policy == "SupplySignal gap":
        return list(cases)
    if policy == "Reported-zero first":
        return sorted(
            cases,
            key=lambda row: (
                row["stock_on_last_report"] == "" or row["stock_on_last_report"] is None,
                float(row["stock_on_last_report"])
                if row["stock_on_last_report"] not in ("", None) else float("inf"),
                row["facility_id"], row["commodity_id"],
            ),
        )
    return sorted(
        cases,
        key=lambda row: (
            row["last_report_period"] or "0000-00-00",
            row["facility_id"], row["commodity_id"],
        ),
    )


def score_calls(cases: list[dict], outcomes: dict[tuple[str, str], float], capacity: int) -> dict:
    """Measure only product checks present in the worklist at called PHCs."""
    if capacity <= 0:
        raise ValueError("Call capacity must be positive")
    calls = facility_call_plan(cases, capacity=capacity)
    called_ids = {call["facility_id"] for call in calls}
    checked_pairs = {
        (case["facility_id"], case["commodity_id"])
        for case in cases if case["facility_id"] in called_ids
    }
    hit_pairs = {pair for pair in checked_pairs if outcomes.get(pair, 0) > 0}
    hit_facilities = {facility_id for facility_id, _ in hit_pairs}
    all_event_pairs = {pair for pair, unmet in outcomes.items() if unmet > 0}
    event_facilities = {facility_id for facility_id, _ in all_event_pairs}
    candidate_pairs = {(case["facility_id"], case["commodity_id"]) for case in cases}
    candidate_facilities = {facility_id for facility_id, _ in candidate_pairs}
    candidate_hit_pairs = all_event_pairs & candidate_pairs
    candidate_hit_facilities = {facility_id for facility_id, _ in candidate_hit_pairs}
    n_candidates = len(candidate_facilities)
    call_count = len(calls)
    return {
        "facility_calls": call_count,
        "product_checks": len(checked_pairs),
        "shortage_calls": len(hit_facilities),
        "calls_without_shortage": call_count - len(hit_facilities),
        "shortage_product_checks": len(hit_pairs),
        "missed_shortage_products": len(all_event_pairs - hit_pairs),
        "missed_shortage_facilities": len(event_facilities - hit_facilities),
        "unmet_units_found": sum(outcomes[pair] for pair in hit_pairs),
        "total_unmet_units": sum(outcomes.values()),
        "event_products": len(all_event_pairs),
        "event_facilities": len(event_facilities),
        "candidate_products": len(candidate_pairs),
        "candidate_facilities": n_candidates,
        "candidate_event_products": len(candidate_hit_pairs),
        "random_candidate_expected_shortage_calls": (
            call_count * len(candidate_hit_facilities) / n_candidates if n_candidates else 0
        ),
        "random_candidate_expected_product_hits": (
            call_count * len(candidate_hit_pairs) / n_candidates if n_candidates else 0
        ),
        "random_candidate_expected_product_checks": (
            call_count * len(candidate_pairs) / n_candidates if n_candidates else 0
        ),
    }


def evaluate(ledger: pd.DataFrame, groups: dict[str, tuple[list[date], str]], capacity: int = 10,
             ledger_path: Path = DEFAULT_LEDGER) -> dict:
    if "truth_unmet_units" not in ledger:
        raise ValueError("Complete simulator truth is required; never infer missing outcomes as zero")
    months = []
    for group, (dates, forecast_strategy) in groups.items():
        for as_of in dates:
            truth = ledger[ledger["period"] == as_of.isoformat()]
            if truth.empty or truth["truth_unmet_units"].isna().any():
                raise ValueError(f"Complete simulator truth unavailable for {as_of}")
            outcomes = {
                (row.facility_id, row.commodity_id): float(row.truth_unmet_units)
                for row in truth.itertuples()
            }
            cases = create_queue(
                as_of, priority_policy="absolute_gap", forecast_strategy=forecast_strategy,
                ledger_path=ledger_path,
            )
            for policy in POLICIES:
                scored = score_calls(order_cases(cases, policy), outcomes, capacity)
                months.append({
                    "group": group, "period": as_of.isoformat(), "forecast_strategy": forecast_strategy,
                    "policy": policy, **scored,
                })
    summary = []
    additive = (
        "facility_calls", "product_checks", "shortage_calls", "calls_without_shortage",
        "shortage_product_checks", "missed_shortage_products", "missed_shortage_facilities",
        "unmet_units_found", "total_unmet_units", "event_products", "event_facilities",
        "candidate_products", "candidate_facilities", "candidate_event_products",
        "random_candidate_expected_shortage_calls", "random_candidate_expected_product_hits",
        "random_candidate_expected_product_checks",
    )
    for group in groups:
        for policy in POLICIES:
            selected = [row for row in months if row["group"] == group and row["policy"] == policy]
            totals = {key: sum(row[key] for row in selected) for key in additive}
            summary.append({
                "group": group, "forecast_strategy": selected[0]["forecast_strategy"] if selected else "",
                "policy": policy, "periods": len(selected), **totals,
                "shortage_call_yield": round(totals["shortage_calls"] / totals["facility_calls"], 4)
                if totals["facility_calls"] else None,
                "product_hit_rate_per_check": round(
                    totals["shortage_product_checks"] / totals["product_checks"], 4
                ) if totals["product_checks"] else None,
                "product_recall": round(totals["shortage_product_checks"] / totals["event_products"], 4)
                if totals["event_products"] else None,
                "unmet_unit_capture": round(totals["unmet_units_found"] / totals["total_unmet_units"], 4)
                if totals["total_unmet_units"] else None,
            })
    return {
        "status": "RETROSPECTIVE SIMULATION ONLY; every period and simulator design have been inspected",
        "capacity": capacity,
        "comparison": "same flagged candidates, ten unique PHC calls, every flagged product at a called PHC checked",
        "forecast_comparison": "Earlier dates use three-report mean; later dates show both mean and trained model",
        "outcome": "simulator truth_unmet_units > 0 in the decision month",
        "random_reference": "analytical expectation from uniformly selecting eligible candidate PHCs; not a deployable policy",
        "important_limit": "A shortage in a product absent from the call plan is a miss even if the PHC is called",
        "summary": summary,
        "monthly": months,
    }


def run(report_path: Path = DEFAULT_REPORT, ledger_path: Path = DEFAULT_LEDGER) -> dict:
    ledger = pd.read_csv(ledger_path)
    report = evaluate(ledger, GROUPS, ledger_path=ledger_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    args = parser.parse_args()
    report = run(args.report, args.ledger)
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    from .logging_config import run_cli

    run_cli(main)
