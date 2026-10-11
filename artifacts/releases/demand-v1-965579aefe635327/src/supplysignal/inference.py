"""Load a fitted demand artifact and score a new decision date."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .features import model_matrix, prepare_ledger, snapshot_features
from .train import DEFAULT_ARTIFACT, DEFAULT_LEDGER

logger = logging.getLogger("supplysignal.inference")


def predict(
    ledger_path: Path,
    artifact_path: Path,
    target_period: str,
    as_of: str,
    roster_path: Path | None = None,
) -> pd.DataFrame:
    artifact = joblib.load(artifact_path)
    ledger = prepare_ledger(pd.read_csv(ledger_path))
    roster = pd.read_csv(roster_path) if roster_path else None
    features = snapshot_features(ledger, target_period, as_of, roster)
    chosen = artifact["selected_model"]
    if chosen == "last_report":
        values = features["last_consumption"].fillna(artifact["fallback_median"]).to_numpy(dtype=float)
    elif chosen == "mean_last_3_reports":
        values = features["mean_3_consumption"].fillna(artifact["fallback_median"]).to_numpy(dtype=float)
    else:
        matrix = model_matrix(features, artifact["commodity_vocabulary"])
        if list(matrix.columns) != artifact["feature_columns"]:
            raise ValueError("Inference feature schema differs from training")
        values = artifact["model"].predict(matrix)
    result = features[
        ["facility_id", "commodity_id", "target_period", "as_of", "last_closing_stock", "report_age_months", "visible_reports_last_3"]
    ].copy()
    result["forecast_demand_units"] = np.maximum(0, values)
    result["model_name"] = chosen
    result["model_provenance"] = artifact["source_provenance"]
    result["requires_verification"] = result["report_age_months"].isna() | result["report_age_months"].gt(1)
    logger.debug("inference_completed", extra={"context": {
        "model": chosen, "rows": len(result),
        "requires_verification": int(result["requires_verification"].sum()),
    }})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--target-period", default="2026-10-01")
    parser.add_argument("--as-of", default="2026-10-04")
    parser.add_argument("--roster", type=Path, help="Expected facility × commodity pairs, including silent facilities")
    parser.add_argument("--output", type=Path, default=Path("data/processed/current_forecasts.csv"))
    args = parser.parse_args()
    result = predict(args.ledger, args.artifact, args.target_period, args.as_of, args.roster)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    print(json.dumps({"rows": len(result), "model": result["model_name"].iloc[0], "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    from .logging_config import run_cli

    run_cli(main)
