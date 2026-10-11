"""Download the public facility extract needed by the demonstration pipeline."""

from __future__ import annotations

import argparse
import io
import json
import logging
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zipfile import is_zipfile


RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
logger = logging.getLogger("supplysignal.fetch_sources")
NHFS_URL = "https://microdata.nigerianstat.gov.ng/index.php/catalog/149/download/1094"
LAYER = "https://services3.arcgis.com/9nfxWATFamVUTTGb/ArcGIS/rest/services/health_facilities_state_WFL1/FeatureServer/1/query"
PARAMS = {
    "where": "state = 'Oyo' AND lga = 'Afijio' AND ownership = 'Public' AND facility_l = 'Primary'",
    "outFields": "*",
    "returnGeometry": "false",
    "f": "json",
}


def fetch() -> Path:
    request = Request(f"{LAYER}?{urlencode(PARAMS)}", headers={"User-Agent": "PHC-SupplySignal/0.1"})
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("error") or payload.get("exceededTransferLimit") or len(payload.get("features", [])) < 20:
        raise ValueError("Facility query failed or returned an incomplete result")
    RAW.mkdir(parents=True, exist_ok=True)
    destination = RAW / "afijio_public_primary_arcgis.json"
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    logger.info("registry_downloaded", extra={"context": {"records": len(payload["features"])}})
    return destination


def fetch_nhfs() -> Path:
    request = Request(NHFS_URL, headers={"User-Agent": "PHC-SupplySignal/0.1"})
    with urlopen(request, timeout=60) as response:
        data = response.read()
    if not is_zipfile(io.BytesIO(data)):
        raise ValueError("NBS response is not an XLSX workbook")
    RAW.mkdir(parents=True, exist_ok=True)
    destination = RAW / "nhfs_2023_results_tables.xlsx"
    destination.write_bytes(data)
    logger.info("nhfs_downloaded", extra={"context": {"bytes": len(data)}})
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-nhfs", action="store_true")
    args = parser.parse_args()
    print(fetch())
    if args.include_nhfs:
        print(fetch_nhfs())


if __name__ == "__main__":
    from .logging_config import run_cli

    run_cli(main)
