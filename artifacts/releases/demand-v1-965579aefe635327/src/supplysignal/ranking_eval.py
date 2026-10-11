"""Backtest verification worklists without using hidden truth for ranking.

Development and validation use only three-report demand forecasts, so the
final demand model (refitted through May 2026) cannot leak into those earlier
decision dates. June--September is exploratory: this project had already
inspected those outcomes before this ranking comparison was written.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

from .decisions import PRIORITY_POLICIES, create_queue, facility_call_plan
from .pipeline import load_facilities, simulate_ledger
from .train import DEFAULT_LEDGER


DEFAULT_REPORT = Path(__file__).resolve().parents[2] / "data" / "processed" / "ranking_report.json"
DEVELOPMENT = [date(2025, month, 1) for month in range(4, 13)] + [date(2026, month, 1) for month in (1, 2)]
VALIDATION = [date(2026, month, 1) for month in (3, 4, 5)]
EXPLORED_TEST = [date(2026, month, 1) for month in (6, 7, 8, 9)]
STRESS_SEEDS = (20261011, 20261017, 20261023, 20261029, 20261103, 20261109)


def evaluate_policy(
    ledger: pd.DataFrame, months: list[date], policy: str,
    *, forecast_strategy: str = "three_report_mean", capacity: int = 10,
    ledger_path: Path = DEFAULT_LEDGER,
) -> dict:
    if capacity <= 0:
        raise ValueError("Verification capacity must be positive")
    if "truth_unmet_units" not in ledger:
        raise ValueError("Synthetic truth is required for this offline evaluation")
    by_period = []
    for as_of in months:
        truth = ledger[ledger["period"] == as_of.isoformat()]
        if truth.empty or truth["truth_unmet_units"].isna().any():
            raise ValueError(f"Complete simulation truth unavailable for {as_of}")
        outcomes = {
            (row.facility_id, row.commodity_id): float(row.truth_unmet_units)
            for row in truth.itertuples()
        }
        queue = create_queue(
            as_of, priority_policy=policy, forecast_strategy=forecast_strategy,
            ledger_path=ledger_path,
        )
        top = queue[:capacity]
        calls = facility_call_plan(queue, capacity)
        facility_outcomes = truth.groupby("facility_id")["truth_unmet_units"].sum()
        candidate_facilities = {row["facility_id"] for row in queue}
        called_facilities = {row["facility_id"] for row in calls}
        event_facilities = {facility_id for facility_id, unmet in facility_outcomes.items() if unmet > 0}
        candidate_unmet = sum(outcomes.get((row["facility_id"], row["commodity_id"]), 0) for row in queue)
        top_unmet = sum(outcomes.get((row["facility_id"], row["commodity_id"]), 0) for row in top)
        events = sum(value > 0 for value in outcomes.values())
        candidate_events = sum(outcomes.get((row["facility_id"], row["commodity_id"]), 0) > 0 for row in queue)
        hits = sum(outcomes.get((row["facility_id"], row["commodity_id"]), 0) > 0 for row in top)
        by_period.append({
            "period": as_of.isoformat(), "eligible_pairs": len(outcomes),
            "candidate_cases": len(queue), "event_cases": events,
            "candidate_event_cases": candidate_events, "top_k_cases": len(top),
            "top_k_hits": hits, "total_unmet_units": sum(outcomes.values()),
            "candidate_unmet_units": candidate_unmet, "top_k_unmet_units": top_unmet,
            "random_all_expected_hits": len(top) * events / len(outcomes),
            "random_candidate_expected_hits": len(top) * candidate_events / len(queue) if queue else 0,
            "facility_calls": len(calls),
            "facility_event_cases": len(event_facilities),
            "facility_call_hits": len(called_facilities & event_facilities),
            "flagged_products_at_called_facilities": sum(row["case_count"] for row in calls),
            "random_candidate_expected_facility_hits": (
                len(calls) * len(candidate_facilities & event_facilities) / len(candidate_facilities)
                if candidate_facilities else 0
            ),
        })
    total = lambda field: sum(row[field] for row in by_period)
    return {
        "policy": policy, "forecast_strategy": forecast_strategy, "capacity_per_period": capacity,
        "periods": len(by_period), "eligible_pairs": total("eligible_pairs"),
        "candidate_cases": total("candidate_cases"), "event_cases": total("event_cases"),
        "candidate_event_cases": total("candidate_event_cases"),
        "top_k_cases": total("top_k_cases"), "top_k_hits": total("top_k_hits"),
        "top_k_precision": round(total("top_k_hits") / total("top_k_cases"), 4) if total("top_k_cases") else None,
        "top_k_event_recall": round(total("top_k_hits") / total("event_cases"), 4) if total("event_cases") else None,
        "top_k_unmet_units": total("top_k_unmet_units"),
        "total_unmet_units": total("total_unmet_units"),
        "top_k_unmet_capture": round(total("top_k_unmet_units") / total("total_unmet_units"), 4)
        if total("total_unmet_units") else None,
        "random_all_expected_hits": round(total("random_all_expected_hits"), 2),
        "random_candidate_expected_hits": round(total("random_candidate_expected_hits"), 2),
        "facility_calls": total("facility_calls"),
        "facility_event_cases": total("facility_event_cases"),
        "facility_call_hits": total("facility_call_hits"),
        "facility_call_precision": round(total("facility_call_hits") / total("facility_calls"), 4)
        if total("facility_calls") else None,
        "facility_call_recall": round(total("facility_call_hits") / total("facility_event_cases"), 4)
        if total("facility_event_cases") else None,
        "flagged_products_at_called_facilities": total("flagged_products_at_called_facilities"),
        "random_candidate_expected_facility_hits": round(total("random_candidate_expected_facility_hits"), 2),
        "monthly": by_period,
    }


def receipt_stress_test() -> dict:
    """Check a receipt-aware challenger across fixed alternate simulator seeds."""
    facilities = load_facilities()
    by_seed = []
    with tempfile.TemporaryDirectory() as directory:
        ledger_path = Path(directory) / "stress_ledger.csv"
        for seed in STRESS_SEEDS:
            ledger = pd.DataFrame(simulate_ledger(facilities, seed=seed))
            ledger.to_csv(ledger_path, index=False)
            baseline = evaluate_policy(ledger, EXPLORED_TEST, "absolute_gap", ledger_path=ledger_path)
            challenger = evaluate_policy(ledger, EXPLORED_TEST, "receipt_gap", ledger_path=ledger_path)
            by_seed.append({
                "seed": seed,
                "event_cases": baseline["event_cases"],
                "baseline_top_10_hits": baseline["top_k_hits"],
                "receipt_top_10_hits": challenger["top_k_hits"],
                "baseline_unmet_units_in_top_10": baseline["top_k_unmet_units"],
                "receipt_unmet_units_in_top_10": challenger["top_k_unmet_units"],
                "baseline_facility_call_hits": baseline["facility_call_hits"],
                "receipt_facility_call_hits": challenger["facility_call_hits"],
            })
    return {
        "description": "Fixed alternate seeds of the same simulator; not independent Nigerian facility data",
        "periods_per_seed": len(EXPLORED_TEST),
        "top_10_product_hits": {
            "absolute_gap": sum(row["baseline_top_10_hits"] for row in by_seed),
            "receipt_gap": sum(row["receipt_top_10_hits"] for row in by_seed),
        },
        "top_10_unmet_units": {
            "absolute_gap": sum(row["baseline_unmet_units_in_top_10"] for row in by_seed),
            "receipt_gap": sum(row["receipt_unmet_units_in_top_10"] for row in by_seed),
        },
        "facility_call_hits": {
            "absolute_gap": sum(row["baseline_facility_call_hits"] for row in by_seed),
            "receipt_gap": sum(row["receipt_facility_call_hits"] for row in by_seed),
        },
        "by_seed": by_seed,
    }


def run(report_path: Path = DEFAULT_REPORT) -> dict:
    ledger = pd.read_csv(DEFAULT_LEDGER)
    development = {
        policy: evaluate_policy(ledger, DEVELOPMENT, policy) for policy in PRIORITY_POLICIES
    }
    # Selection is frozen using only earlier months. The simpler original rule
    # wins ties, rather than exploiting arbitrary score precision.
    selected = max(
        PRIORITY_POLICIES,
        key=lambda policy: (
            development[policy]["top_k_hits"],
            development[policy]["top_k_unmet_units"],
            -PRIORITY_POLICIES.index(policy),
        ),
    )
    validation = {
        policy: evaluate_policy(ledger, VALIDATION, policy)
        for policy in dict.fromkeys(("absolute_gap", selected, "receipt_gap"))
    }
    explored_test = {
        policy: evaluate_policy(ledger, EXPLORED_TEST, policy, forecast_strategy="model")
        for policy in dict.fromkeys(("absolute_gap", selected, "receipt_gap"))
    }
    candidate_validation = validation[selected]
    baseline_validation = validation["absolute_gap"]
    passed = (
        selected != "absolute_gap"
        and candidate_validation["top_k_hits"] > baseline_validation["top_k_hits"]
        and candidate_validation["top_k_hits"] > candidate_validation["random_candidate_expected_hits"]
    )
    report = {
        "evaluation": "SIMULATION ONLY; not evidence of Nigerian field performance",
        "selection_rule": "Highest development top-10 event hits, then unmet units captured, then simpler policy",
        "selected_policy": selected,
        "deployment_gate": {
            "candidate_accepted": passed,
            "deployed_policy": selected if passed else "absolute_gap",
            "reason": "Original coverage candidate beat the baseline and random-candidate expectation on its then-untouched March-May check"
            if passed else "Original coverage candidate failed its then-untouched March-May check; retain the baseline as an exploratory worklist",
            "worklist_validated_for_field_use": False,
        },
        "development": development,
        "validation_untouched_during_selection": validation,
        "exploratory_test_already_inspected": explored_test,
        "receipt_challenger_stress_test": receipt_stress_test(),
        "limitations": [
            "No real facility-level inventory or prospectively verified shortages",
            "The historical validation and June-September outcomes have been inspected during successive ranking experiments; neither is an untouched test for new challengers",
            "Alternate seeds share one simulator design and scripted scenarios; they are a robustness check, not independent external validation",
            "Synthetic receipt timing may dominate simulated stockout outcomes",
            "Facility-call hits assume an officer checks all flagged products during a call; this costs more product checks than a one-product call",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = run(args.report)
    print(json.dumps({
        "selected_policy": report["selected_policy"],
        "deployment_gate": report["deployment_gate"],
        "development": {key: value["top_k_hits"] for key, value in report["development"].items()},
        "validation": {key: value["top_k_hits"] for key, value in report["validation_untouched_during_selection"].items()},
        "exploratory_test": {key: value["top_k_hits"] for key, value in report["exploratory_test_already_inspected"].items()},
    }, indent=2))


if __name__ == "__main__":
    from .logging_config import run_cli

    run_cli(main)
