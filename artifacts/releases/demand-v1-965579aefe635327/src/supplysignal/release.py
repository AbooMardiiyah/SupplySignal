"""Package a locally trained model, its data, code and exact training lineage."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import tempfile
from importlib.metadata import distributions
from pathlib import Path

import joblib
import numpy as np

from .inference import predict
from .train import DEFAULT_ARTIFACT, DEFAULT_LEDGER, DEFAULT_PREDICTIONS, DEFAULT_REPORT
from .versioning import sha256

ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger("supplysignal.release")


def verify(directory: Path) -> dict:
    manifest = json.loads((directory / "bundle.json").read_text())
    for name, expected in manifest["files_sha256"].items():
        path = directory / name
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"Release checksum mismatch: {name}")
    return manifest


def package(artifact: Path, ledger: Path, report: Path, predictions: Path,
            output: Path = ROOT / "artifacts/releases") -> Path:
    lineage_path = artifact.with_suffix(".manifest.json")
    lineage = json.loads(lineage_path.read_text())
    for path, key in ((artifact, "artifact_sha256"), (ledger, "ledger_sha256"),
                      (report, "report_sha256"), (predictions, "predictions_sha256")):
        if sha256(path) != lineage[key]:
            raise ValueError(f"Training lineage mismatch: {path.name}")
    for name, expected in lineage["training_source_sha256"].items():
        if sha256(Path(__file__).parent / name) != expected:
            raise ValueError(f"Training source changed since fit: {name}; rerun the experiment")
    # Only the project's own trusted artifact is loaded here.
    fitted = joblib.load(artifact)
    if fitted["release_identity"] != {k: v for k, v in lineage.items()
                                     if k not in {"artifact_sha256", "report_sha256", "predictions_sha256"}}:
        raise ValueError("Embedded model identity differs from sidecar")
    destination = output / lineage["model_version"]
    if destination.exists():
        existing = verify(destination)
        if existing["artifact_sha256"] != lineage["artifact_sha256"]:
            raise ValueError("Existing version has different model bytes; do not overwrite")
        return destination
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="release-", dir=output) as temp:
        stage = Path(temp)
        files = {
            "artifacts/demand_model.joblib": artifact,
            "artifacts/demand_model.manifest.json": lineage_path,
            "data/processed/synthetic_lmis.csv": ledger,
            "data/processed/training_report.json": report,
            "data/processed/test_predictions.csv": predictions,
            "data/processed/facilities.csv": ROOT / "data/processed/facilities.csv",
            "data/processed/manifest.json": ROOT / "data/processed/manifest.json",
            "data/raw/afijio_public_primary_arcgis.json": ROOT / "data/raw/afijio_public_primary_arcgis.json",
            "pyproject.toml": ROOT / "pyproject.toml",
        }
        for path in sorted((ROOT / "src/supplysignal").glob("*.py")):
            files[str(path.relative_to(ROOT))] = path
        for name, path in files.items():
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        environment = sorted({f"{dist.metadata['Name']}=={dist.version}"
                              for dist in distributions()
                              if dist.metadata['Name'].lower().replace('_', '-') != "phc-supplysignal"})
        (stage / "requirements-executed.txt").write_text("\n".join(environment) + "\n")
        sample = predict(ledger, artifact, "2026-10-01", "2026-10-04")
        restored = predict(stage / "data/processed/synthetic_lmis.csv",
                           stage / "artifacts/demand_model.joblib", "2026-10-01", "2026-10-04")
        np.testing.assert_allclose(sample.forecast_demand_units, restored.forecast_demand_units,
                                   rtol=0, atol=0)
        sample.to_csv(stage / "sample_forecasts.csv", index=False)
        (stage / "README.md").write_text(
            "# SupplySignal simulation model release\n\n"
            f"Version: {lineage['model_version']}\n\n"
            "This is a simulation prototype, not validated for field decisions.\n"
            "The registry snapshot is real; every inventory observation is simulated.\n\n"
            f"Executed Python: {lineage['python']}. Create a compatible virtual environment.\n"
            "Install requirements-executed.txt, then `pip install --no-deps -e .`.\n"
            "Run `python -m supplysignal.release --verify .` to check file integrity.\n"
            "Run `python -m supplysignal.inference` to reproduce the sample forecasts.\n"
            "Run `python -m supplysignal.train` to reproduce the fixed experiment.\n\n"
            "The environment snapshot records installed versions; it is not a cross-platform lockfile.\n"
            "Public-source attribution and snapshot hash are in data/processed/manifest.json.\n"
            "Local packaging does not establish permission to redistribute third-party data publicly.\n"
        )
        manifest = {
            "model_version": lineage["model_version"],
            "artifact_sha256": lineage["artifact_sha256"],
            "status": "SIMULATION PROTOTYPE; no field validation",
            "load_parity_rows": len(sample),
            "files_sha256": {str(p.relative_to(stage)): sha256(p)
                             for p in sorted(stage.rglob("*")) if p.is_file()},
        }
        (stage / "bundle.json").write_text(json.dumps(manifest, indent=2) + "\n")
        verify(stage)
        stage.rename(destination)
    shutil.make_archive(str(destination), "zip", destination)
    logger.info("release_packaged", extra={"context": {
        "model_version": lineage["model_version"], "parity_rows": len(sample),
    }})
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/releases")
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.verify:
        result = verify(args.verify)
        print(json.dumps({"verified": result["model_version"], "files": len(result["files_sha256"])}))
    else:
        print(package(args.artifact, args.ledger, args.report, args.predictions, args.output))


if __name__ == "__main__":
    from .logging_config import run_cli

    run_cli(main)
