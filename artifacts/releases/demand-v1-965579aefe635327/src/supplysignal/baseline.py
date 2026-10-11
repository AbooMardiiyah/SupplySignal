"""Leakage-safe, one-month demand baselines on the simulated ledger."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "data" / "processed" / "synthetic_lmis.csv"
OUTPUT = ROOT / "data" / "processed" / "baseline_results.json"


def evaluate(path: Path = LEDGER) -> dict:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("No ledger rows")
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["facility_id"], row["commodity_id"])].append(row)
    errors = {"last_report": [], "mean_last_3_reports": []}
    cases = 0
    skipped = 0
    for series in grouped.values():
        series.sort(key=lambda row: row["period"])
        for cutoff in range(13, len(series) - 1):
            as_of = date.fromisoformat(series[cutoff + 1]["period"])
            observed = [
                int(row["consumption"])
                for row in series[: cutoff + 1]
                if row["report_status"] == "reported"
                and date.fromisoformat(row["submitted_at"]) <= as_of
            ]
            if not observed:
                skipped += 1
                continue
            truth = int(series[cutoff + 1]["truth_latent_demand"])
            predictions = {
                "last_report": observed[-1],
                "mean_last_3_reports": sum(observed[-3:]) / len(observed[-3:]),
            }
            for name, prediction in predictions.items():
                errors[name].append((abs(truth - prediction), prediction - truth, truth))
            cases += 1
    result = {"evaluation": "simulation only", "cases": cases, "skipped": skipped}
    for name, values in errors.items():
        result[name] = {
            "mae": round(sum(v[0] for v in values) / len(values), 3),
            "wape": round(sum(v[0] for v in values) / sum(v[2] for v in values), 4),
            "bias_units": round(sum(v[1] for v in values) / len(values), 3),
        }
    return result


def main() -> None:
    result = evaluate()
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    from .logging_config import run_cli

    run_cli(main)
