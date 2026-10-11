"""Build a reproducible Afijio demonstration from public facility records.

The operational ledger emitted here is synthetic. Real registry attributes are
kept separate from synthetic inventory records in both files and provenance.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "afijio_public_primary_arcgis.json"
PROCESSED = ROOT / "data" / "processed"
SEED = 20261004
MONTHS = 24
COMMODITIES = (
    ("oxytocin", "Oxytocin injection, example unit", 12),
    ("magnesium_sulfate", "Magnesium sulfate injection, example unit", 5),
    ("misoprostol", "Misoprostol tablet, example unit", 18),
)


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"No rows to write: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _month_start(year: int, month: int, offset: int) -> date:
    index = year * 12 + month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def load_facilities(path: Path = RAW) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("error") or payload.get("exceededTransferLimit"):
        raise ValueError("Incomplete or failed facility registry response")
    result = []
    seen = set()
    for feature in payload["features"]:
        item = feature["attributes"]
        if not (
            item["state"] == "Oyo"
            and item["lga"] == "Afijio"
            and item["ownership"] == "Public"
            and item["facility_2"] == "Primary Health Center"
        ):
            continue
        # NHFR codes in this public layer can be missing or duplicated. The
        # ArcGIS globalid identifies records without collapsing distinct PHCs.
        facility_id = item["globalid"]
        if not facility_id or facility_id in seen:
            raise ValueError("Missing or duplicate ArcGIS globalid")
        seen.add(facility_id)
        lat, lon = item["latitude"], item["longitude"]
        if lat is None or lon is None or not (4 < lat < 14 and 2 < lon < 15):
            raise ValueError(f"Invalid facility coordinates: {facility_id}")
        result.append(
            {
                "facility_id": facility_id,
                "nhfr_code": (item["nhfr_facil"] or "").strip(),
                "facility_name": item["facility_n"],
                "state": item["state"],
                "lga": item["lga"],
                "ward": item["ward"],
                "facility_type": item["facility_2"],
                "latitude": lat,
                "longitude": lon,
                "source": "GRID3/NHFR ArcGIS 2026-08-21",
                "provenance": "observed_registry",
            }
        )
    return sorted(result, key=lambda r: r["facility_id"])


def simulate_ledger(facilities: list[dict], seed: int = SEED) -> list[dict]:
    """Create a small eventful stock ledger with separate truth and reports.

    These parameters are illustrative, not estimated from Nigerian LMIS data.
    `latent_demand` remains in truth even when stock is insufficient; reported
    `consumption` is capped by available stock.
    """
    rng = random.Random(seed)
    rows = []
    for facility_index, facility in enumerate(facilities):
        volume_factor = rng.uniform(0.55, 1.7)
        for commodity_id, commodity_name, base in COMMODITIES:
            stock = int(base * volume_factor * rng.uniform(1.2, 2.5))
            for t in range(MONTHS):
                period = _month_start(2024, 10, t)
                seasonal = 1.15 if period.month in (6, 7, 8, 9) else 1.0
                demand = max(1, round(base * volume_factor * seasonal * rng.uniform(0.7, 1.3)))
                # Deliberate demo scenarios in the latest two periods.
                low_stock = facility_index == 0 and commodity_id == "oxytocin" and t >= 22
                silent = facility_index == 1 and commodity_id == "magnesium_sulfate" and t >= 22
                potential_donor = facility_index == 2 and commodity_id == "oxytocin" and t >= 21
                no_donor = facility_index == 3 and commodity_id == "misoprostol" and t >= 22
                if low_stock or no_donor:
                    receipts = 0
                elif potential_donor:
                    receipts = 4 * demand
                elif stock < 2 * demand:
                    receipts = (
                        0
                        if rng.random() < 0.1
                        else max(0, round(demand * rng.uniform(2.0, 3.5)) - stock)
                    )
                else:
                    receipts = 0
                opening = stock
                available = opening + receipts
                consumed = min(demand, available)
                stock = available - consumed
                report_missing = silent or rng.random() < 0.045
                report_lag_days = rng.choice((2, 4, 7, 14, 29))
                if rng.random() < 0.08:
                    report_lag_days += 30
                if t == MONTHS - 1 and (low_stock or potential_donor or no_donor):
                    report_missing = False
                    report_lag_days = 2
                rows.append(
                    {
                        "facility_id": facility["facility_id"],
                        "commodity_id": commodity_id,
                        "commodity_name": commodity_name,
                        "period": period.isoformat(),
                        "opening_stock": "" if report_missing else opening,
                        "receipts": "" if report_missing else receipts,
                        "consumption": "" if report_missing else consumed,
                        "losses": "" if report_missing else 0,
                        "adjustments": "" if report_missing else 0,
                        "closing_stock": "" if report_missing else stock,
                        "stockout_days": ""
                        if report_missing
                        else (max(1, round(30 * (demand - consumed) / demand)) if consumed < demand else 0),
                        "report_status": "missing" if report_missing else "reported",
                        "submitted_at": ""
                        if report_missing
                        else (period + timedelta(days=31 + report_lag_days)).isoformat(),
                        "source": "seeded_lmis_simulator_v1",
                        "provenance": "simulated",
                        # Truth-only columns are used for simulation evaluation.
                        # They must never be fed to a forecasting model.
                        "truth_latent_demand": demand,
                        "truth_unmet_units": demand - consumed,
                    }
                )
    return sorted(rows, key=lambda r: (r["period"], r["facility_id"], r["commodity_id"]))


def validate_ledger(rows: list[dict], facility_count: int) -> None:
    expected = facility_count * len(COMMODITIES) * MONTHS
    if len(rows) != expected:
        raise ValueError(f"Expected {expected} facility-commodity-period rows")
    keys = set()
    for row in rows:
        key = row["facility_id"], row["commodity_id"], row["period"]
        if key in keys:
            raise ValueError(f"Duplicate ledger key: {key}")
        keys.add(key)
        if row["report_status"] == "missing":
            if any(row[field] != "" for field in ("opening_stock", "receipts", "consumption", "closing_stock", "submitted_at")):
                raise ValueError(f"Missing report contains observed stock: {key}")
            continue
        opening = int(row["opening_stock"])
        receipts = int(row["receipts"])
        consumption = int(row["consumption"])
        closing = int(row["closing_stock"])
        if min(opening, receipts, consumption, closing) < 0:
            raise ValueError(f"Negative stock quantity: {key}")
        if closing != opening + receipts - consumption:
            raise ValueError(f"Unbalanced stock ledger: {key}")


def build() -> dict:
    facilities = load_facilities()
    if len(facilities) < 10:
        raise ValueError("Too few public PHCs for pilot")
    ledger = simulate_ledger(facilities)
    validate_ledger(ledger, len(facilities))
    PROCESSED.mkdir(parents=True, exist_ok=True)
    _write_csv(PROCESSED / "facilities.csv", facilities)
    _write_csv(PROCESSED / "synthetic_lmis.csv", ledger)
    counts = defaultdict(int)
    for row in ledger:
        counts[row["report_status"]] += 1
    manifest = {
        "pilot": "Afijio LGA, Oyo State",
        "facility_count": len(facilities),
        "missing_nhfr_codes": sum(not item["nhfr_code"] for item in facilities),
        "duplicate_nhfr_codes": sorted(
            {
                item["nhfr_code"]
                for item in facilities
                if item["nhfr_code"]
                and sum(other["nhfr_code"] == item["nhfr_code"] for other in facilities) > 1
            }
        ),
        "commodity_count": len(COMMODITIES),
        "months": MONTHS,
        "operational_row_count": len(ledger),
        "report_status_counts": dict(counts),
        "seed": SEED,
        "real_facility_source": "GRID3 ArcGIS layer, NHFR 2024 inputs, updated 2026-08-21",
        "real_facility_source_url": "https://services3.arcgis.com/9nfxWATFamVUTTGb/ArcGIS/rest/services/health_facilities_state_WFL1/FeatureServer/1",
        "operational_source": "simulated; no Nigerian facility inventory observations",
        "nhfs_context": "Oyo public primary mean essential-drug availability 43.2107% in 2023; state aggregate, not facility or commodity level",
        "nhfs_source_url": "https://microdata.nigerianstat.gov.ng/index.php/catalog/149/related-materials",
        "raw_registry_sha256": hashlib.sha256(RAW.read_bytes()).hexdigest(),
    }
    (PROCESSED / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    print(json.dumps(build(), indent=2))


if __name__ == "__main__":
    from .logging_config import run_cli

    run_cli(main)
