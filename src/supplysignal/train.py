"""Benchmark global demand models and freeze a future-period test result.

Model labels are reported consumption only when stockout_days=0 and closing
stock > 0. Synthetic latent demand is reserved for evaluation and never used
to fit a model or create features.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from .features import NUMERIC_FEATURES, Split, build_feature_panel, model_matrix, prepare_ledger
from .versioning import sha256, training_identity


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = ROOT / "data" / "processed" / "synthetic_lmis.csv"
DEFAULT_ARTIFACT = ROOT / "artifacts" / "demand_model.joblib"
DEFAULT_REPORT = ROOT / "data" / "processed" / "training_report.json"
DEFAULT_PREDICTIONS = ROOT / "data" / "processed" / "test_predictions.csv"
FIRST_TARGET = "2025-04-01"
SPLIT = Split()
logger = logging.getLogger("supplysignal.train")


def _metrics(truth: np.ndarray, predictions: np.ndarray) -> dict:
    mask = np.isfinite(truth) & np.isfinite(predictions)
    actual, predicted = truth[mask], predictions[mask]
    if not len(actual):
        return {"n": 0, "mae": None, "wape": None, "bias_units": None}
    errors = predicted - actual
    return {
        "n": int(len(actual)),
        "mae": round(float(np.mean(np.abs(errors))), 4),
        "wape": round(float(np.abs(errors).sum() / actual.sum()), 4) if actual.sum() else None,
        "bias_units": round(float(errors.mean()), 4),
    }


def _baseline(frame: pd.DataFrame, name: str, fallback: float) -> np.ndarray:
    source = "last_consumption" if name == "last_report" else "mean_3_consumption"
    return frame[source].fillna(fallback).clip(lower=0).to_numpy(dtype=float)


def _candidate_models() -> dict:
    candidates = {
        "hist_gradient_boosting": HistGradientBoostingRegressor(
            loss="poisson", max_iter=180, max_leaf_nodes=15,
            min_samples_leaf=20, learning_rate=0.05,
            early_stopping=False, random_state=42,
        )
    }
    try:
        from lightgbm import LGBMRegressor

        candidates["lightgbm"] = LGBMRegressor(
            objective="poisson", n_estimators=180, learning_rate=0.05,
            num_leaves=15, min_child_samples=20, verbosity=-1,
            random_state=42, n_jobs=2,
        )
    except ImportError:
        logger.warning("optional_lightgbm_unavailable")
    return candidates


def _fit_rows(panel: pd.DataFrame, end: pd.Timestamp, label_deadline: pd.Timestamp) -> pd.DataFrame:
    return panel[
        (panel["target_period"] <= end)
        & panel["label_uncensored"]
        & (panel["label_submitted_at"] <= label_deadline)
    ]


def _alert_metrics(frame: pd.DataFrame, predicted: np.ndarray) -> dict:
    if frame["truth_stockout"].isna().all():
        return {"note": "Stockout outcomes unavailable; prospective evaluation required"}
    actual = frame["truth_stockout"].astype(bool).to_numpy()
    stock = frame["last_closing_stock"].to_numpy(dtype=float)
    age = frame["report_age_months"].to_numpy(dtype=float)
    # A two-month-old count is usable only as an investigation signal. We
    # project consumption through the unreported month and the target month;
    # future receipts remain unknown, so this is not a confirmed shortage.
    eligible = np.isfinite(stock) & np.isfinite(age) & (age <= 2)
    projected_deficit = age * predicted - stock
    alert = eligible & (projected_deficit > 0)
    tp = int((alert & actual).sum())
    fp = int((alert & ~actual).sum())
    fn = int((~alert & actual & eligible).sum())
    top_hits = []
    for _, group in frame.assign(score=projected_deficit, actual=actual, eligible=eligible).groupby("target_period"):
        top = group[group["eligible"]].nlargest(10, "score")
        if len(top):
            top_hits.append(int(top["actual"].sum()))
    return {
        "eligible_count": int(eligible.sum()),
        "actual_events_total": int(actual.sum()),
        "actual_events_eligible": int((actual & eligible).sum()),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": round(tp / (tp + fp), 4) if tp + fp else None,
        "recall": round(tp / (tp + fn), 4) if tp + fn else None,
        "overall_event_recall": round(tp / actual.sum(), 4) if actual.sum() else None,
        "top_10_hits_per_period": top_hits,
        "note": "Simulation-only stockout evaluation; unknown receipts limit alert precision",
    }


def run(
    ledger_path: Path = DEFAULT_LEDGER,
    artifact_path: Path = DEFAULT_ARTIFACT,
    report_path: Path = DEFAULT_REPORT,
    predictions_path: Path = DEFAULT_PREDICTIONS,
    first_target: str = FIRST_TARGET,
    split: Split = SPLIT,
) -> dict:
    ledger = prepare_ledger(pd.read_csv(ledger_path))
    panel = build_feature_panel(ledger, first_target)
    train_end = pd.Timestamp(split.train_end)
    val_end = pd.Timestamp(split.validation_end)
    test_end = pd.Timestamp(split.test_end)
    first = pd.Timestamp(first_target)
    if not first < train_end < val_end < test_end:
        raise ValueError("Expected first_target < train_end < validation_end < test_end")
    if panel.empty or panel["target_period"].max() < test_end:
        raise ValueError("Ledger does not cover the configured test end")
    panel = panel[panel["target_period"] <= test_end].copy()
    train_deadline = train_end + pd.offsets.MonthBegin(1)
    refit_deadline = val_end + pd.offsets.MonthBegin(1)
    train = _fit_rows(panel, train_end, train_deadline)
    validation = panel[(panel["target_period"] > train_end) & (panel["target_period"] <= val_end)].copy()
    train_val = _fit_rows(panel, val_end, refit_deadline)
    test = panel[(panel["target_period"] > val_end) & (panel["target_period"] <= test_end)].copy()
    if train.empty or validation.empty or test.empty:
        raise ValueError("A chronological split is empty")
    if (train["label_submitted_at"] > train_deadline).any():
        raise AssertionError("Training label leaked across the validation boundary")
    if (train_val["label_submitted_at"] > refit_deadline).any():
        raise AssertionError("Refit label leaked across the test boundary")
    vocabulary = sorted(train["commodity_id"].unique())
    fallback = float(train["label_consumption"].median())
    # On real data, validation is restricted to observed, uncensored periods.
    synthetic = panel["truth_demand"].notna().any()
    if synthetic:
        validation_target = validation["truth_demand"].to_numpy(dtype=float)
        test_target = test["truth_demand"].to_numpy(dtype=float)
    else:
        validation_target = validation["label_consumption"].where(validation["label_uncensored"]).to_numpy(dtype=float)
        test_target = test["label_consumption"].where(test["label_uncensored"]).to_numpy(dtype=float)
    if np.isfinite(validation_target).sum() < 20:
        raise ValueError("Too few observable validation labels")
    models = _candidate_models()
    val_predictions = {
        name: _baseline(validation, name, fallback)
        for name in ("last_report", "mean_last_3_reports")
    }
    x_train = model_matrix(train, vocabulary)
    x_val = model_matrix(validation, vocabulary)
    for name, model in models.items():
        model.fit(x_train, train["label_consumption"].to_numpy(dtype=float))
        val_predictions[name] = np.maximum(0, model.predict(x_val))
    val_scores = {name: _metrics(validation_target, pred) for name, pred in val_predictions.items()}
    chosen = min(val_scores, key=lambda name: val_scores[name]["mae"])
    logger.info("model_selected", extra={"context": {
        "model": chosen, "criterion": "validation_mae",
        "train_rows": len(train), "validation_rows": len(validation),
        "test_rows": len(test), "synthetic": synthetic,
    }})
    # The held-out test is evaluated once after selection. Any fitted model is
    # retrained on eligible train+validation labels available by 1 June 2026.
    final_model = None
    if chosen in models:
        final_model = _candidate_models()[chosen]
        final_model.fit(model_matrix(train_val, vocabulary), train_val["label_consumption"].to_numpy(dtype=float))
    test_predictions = {
        name: _baseline(test, name, fallback)
        for name in ("last_report", "mean_last_3_reports")
    }
    # Benchmark all candidate architectures on the untouched test, using
    # train+validation fits, while selection remains based only on validation.
    for name, model in _candidate_models().items():
        fitted = final_model if name == chosen and final_model is not None else model.fit(
            model_matrix(train_val, vocabulary), train_val["label_consumption"].to_numpy(dtype=float)
        )
        test_predictions[name] = np.maximum(0, fitted.predict(model_matrix(test, vocabulary)))
    test_scores = {name: _metrics(test_target, pred) for name, pred in test_predictions.items()}
    test_by_commodity = {
        commodity: _metrics(
            test_target[test["commodity_id"].eq(commodity).to_numpy()],
            test_predictions[chosen][test["commodity_id"].eq(commodity).to_numpy()],
        )
        for commodity in sorted(test["commodity_id"].unique())
    }
    predictions = test[["facility_id", "commodity_id", "target_period", "last_closing_stock", "report_age_months"]].copy()
    predictions["actual_demand"] = test_target
    predictions["actual_stockout"] = test["truth_stockout"].to_numpy()
    for name, values in test_predictions.items():
        predictions[f"prediction_{name}"] = values
    report = {
        "evaluation": "SIMULATION ONLY" if synthetic else "observed uncensored reports only",
        "split": {
            "train_targets": f"{first.date()} through {split.train_end}",
            "validation_targets": f"{train_deadline.date()} through {split.validation_end}",
            "test_targets": f"{refit_deadline.date()} through {split.test_end}",
            "train_label_deadline": str(train_deadline.date()),
            "refit_label_deadline": str(refit_deadline.date()),
        },
        "row_counts": {"train_fit": len(train), "validation": len(validation), "refit": len(train_val), "test": len(test)},
        "fit_target": "reported consumption from submitted, uncensored months",
        "evaluation_target": "synthetic latent demand" if synthetic else "observed uncensored consumption",
        "feature_columns": list(model_matrix(train, vocabulary).columns),
        "validation_metrics": val_scores,
        "selected_model": chosen,
        "test_metrics": test_scores,
        "selected_test_by_commodity": test_by_commodity,
        "selected_test_alert_metrics": _alert_metrics(test, test_predictions[chosen]),
        "known_limitations": [
            "Demand and labels in this run are simulated; results do not establish Nigerian field accuracy",
            "Unobserved demand during real stockouts needs service-volume or patient-level proxy data",
            "Monthly reporting delay limits the freshness of four-week decisions",
            "Unknown future receipts can create false stockout alerts",
        ],
    }
    artifact = {
        "selected_model": chosen,
        "model": final_model,
        "commodity_vocabulary": vocabulary,
        "feature_columns": list(model_matrix(train, vocabulary).columns),
        "fallback_median": fallback,
        "trained_through": split.validation_end,
        "label_deadline": str(refit_deadline.date()),
        "source_provenance": "simulated" if synthetic else "observed",
    }
    identity = training_identity(ledger_path, {
        "selected_model": chosen,
        "selected_parameters": final_model.get_params() if final_model is not None else {},
        "selection": "lowest validation MAE; test excluded from selection",
        "split": report["split"],
        "features": artifact["feature_columns"],
        "fallback_median": fallback,
        "source_provenance": artifact["source_provenance"],
    })
    artifact["release_identity"] = identity
    report["model_version"] = identity["model_version"]
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, artifact_path)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(predictions_path, index=False)
    artifact_path.with_suffix(".manifest.json").write_text(json.dumps({
        **identity,
        "artifact_sha256": sha256(artifact_path),
        "report_sha256": sha256(report_path),
        "predictions_sha256": sha256(predictions_path),
    }, indent=2) + "\n", encoding="utf-8")
    logger.info("training_artifacts_saved", extra={"context": {
        "model": chosen, "test_wape": test_scores[chosen]["wape"],
    }})
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--first-target", default=FIRST_TARGET)
    parser.add_argument("--train-end", default=SPLIT.train_end)
    parser.add_argument("--validation-end", default=SPLIT.validation_end)
    parser.add_argument("--test-end", default=SPLIT.test_end)
    args = parser.parse_args()
    split = Split(args.train_end, args.validation_end, args.test_end)
    print(json.dumps(run(args.ledger, args.artifact, args.report, args.predictions, args.first_target, split), indent=2))


if __name__ == "__main__":
    from .logging_config import run_cli

    run_cli(main)
