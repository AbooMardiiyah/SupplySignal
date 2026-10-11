"""Content-based identity for a training run; no hosted registry required."""

from __future__ import annotations

import hashlib
import json
import platform
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def training_identity(ledger: Path, configuration: dict) -> dict:
    source = Path(__file__).parent
    packages = {}
    for name in ("numpy", "pandas", "scikit-learn", "lightgbm", "joblib"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    identity = {
        "schema_version": 1,
        "ledger_sha256": sha256(ledger),
        "training_source_sha256": {
            name: sha256(source / name) for name in ("features.py", "train.py", "versioning.py")
        },
        "python": platform.python_version(),
        "packages": packages,
        "configuration": configuration,
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return {"model_version": f"demand-v1-{digest[:16]}", **identity}
