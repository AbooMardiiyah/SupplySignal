"""Normalize a facility × commodity × month LMIS CSV for FTI pipelines.

Source systems use different codes. Pass a JSON mapping from canonical column
name to source column name. No patient data is needed or accepted.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd


REQUIRED = (
    "facility_id",
    "commodity_id",
    "period",
    "consumption",
    "closing_stock",
    "submitted_at",
    "unit",
)
OPTIONAL_NUMERIC = (
    "opening_stock",
    "receipts",
    "losses",
    "adjustments",
    "stockout_days",
)
OPTIONAL_TEXT = ("source", "batch_expiry", "report_status")
logger = logging.getLogger("supplysignal.ingest")


def normalize(input_path: Path, output_path: Path, mapping_path: Path | None = None) -> dict:
    frame = pd.read_csv(input_path, dtype=str, keep_default_na=False)
    if frame.empty:
        raise ValueError("Import contains no monthly reports")
    mapping = json.loads(mapping_path.read_text(encoding="utf-8")) if mapping_path else {}
    if not isinstance(mapping, dict):
        raise ValueError("Column mapping must be a JSON object")
    if any(key not in (*REQUIRED, *OPTIONAL_NUMERIC, *OPTIONAL_TEXT) for key in mapping):
        raise ValueError("Mapping contains an unknown canonical field")
    source_to_canonical = {source: canonical for canonical, source in mapping.items()}
    frame = frame.rename(columns=source_to_canonical)
    if frame.columns.duplicated().any():
        raise ValueError("Column mapping creates duplicate canonical columns")
    missing = sorted(set(REQUIRED) - set(frame))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    # Do not propagate unrelated fields, especially accidental patient-level columns.
    frame = frame[[name for name in (*REQUIRED, *OPTIONAL_NUMERIC, *OPTIONAL_TEXT) if name in frame]]
    for name in OPTIONAL_NUMERIC:
        if name not in frame:
            frame[name] = ""
    for name in OPTIONAL_TEXT:
        if name not in frame:
            frame[name] = ""
    frame["period"] = pd.to_datetime(frame["period"], errors="raise").dt.to_period("M").dt.to_timestamp()
    frame["submitted_at"] = pd.to_datetime(frame["submitted_at"], errors="coerce")
    if frame["submitted_at"].isna().any():
        raise ValueError("Every imported report needs a valid submitted_at timestamp")
    if frame.duplicated(["facility_id", "commodity_id", "period"]).any():
        raise ValueError("Duplicate facility × commodity × period reports require resolution")
    if (frame[["facility_id", "commodity_id"]] == "").any().any():
        raise ValueError("Facility and commodity identifiers cannot be blank")
    if frame["unit"].eq("").any():
        raise ValueError("Every product report needs an explicit stock unit")
    if frame.groupby("commodity_id")["unit"].nunique().gt(1).any():
        raise ValueError("A commodity uses multiple stock units; convert or split product codes first")
    for name in ("consumption", "closing_stock", *OPTIONAL_NUMERIC):
        frame[name] = pd.to_numeric(frame[name].replace("", pd.NA), errors="raise")
        if frame[name].lt(0).any() and name != "adjustments":
            raise ValueError(f"Negative values are invalid in {name}")
    if frame[["consumption", "closing_stock"]].isna().any().any():
        raise ValueError("Submitted reports need consumption and closing stock")
    if frame["stockout_days"].gt(frame["period"].dt.days_in_month).any():
        raise ValueError("Stockout days exceed days in month")
    if frame["submitted_at"].lt(frame["period"]).any():
        raise ValueError("A report cannot be submitted before its reporting month")
    # A physical closing count may differ from the calculated ledger balance.
    # Preserve this discrepancy for investigation instead of overwriting it.
    calculable = frame[["opening_stock", "receipts", "consumption", "losses", "adjustments"]].notna().all(axis=1)
    calculated = frame["opening_stock"] + frame["receipts"] - frame["consumption"] - frame["losses"] + frame["adjustments"]
    frame["balance_discrepancy"] = (frame["closing_stock"] - calculated).where(calculable)
    frame["report_status"] = "reported"
    frame["provenance"] = "observed"
    frame["source"] = frame["source"].replace("", input_path.name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)
    logger.info("import_normalized", extra={"context": {
        "rows": len(frame), "facilities": int(frame["facility_id"].nunique()),
        "balance_discrepancies": int(frame["balance_discrepancy"].fillna(0).ne(0).sum()),
    }})
    return {
        "rows": len(frame),
        "facilities": int(frame["facility_id"].nunique()),
        "commodities": int(frame["commodity_id"].nunique()),
        "first_period": frame["period"].min().date().isoformat(),
        "last_period": frame["period"].max().date().isoformat(),
        "balance_discrepancies": int(frame["balance_discrepancy"].fillna(0).ne(0).sum()),
        "unknown_stockout_days": int(frame["stockout_days"].isna().sum()),
        "output": str(output_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mapping", type=Path)
    args = parser.parse_args()
    print(json.dumps(normalize(args.input, args.output, args.mapping), indent=2))


if __name__ == "__main__":
    from .logging_config import run_cli

    run_cli(main)
