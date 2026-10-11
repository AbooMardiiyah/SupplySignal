# SupplySignal simulation model release

Version: demand-v1-965579aefe635327

This is a simulation prototype, not validated for field decisions.
The registry snapshot is real; every inventory observation is simulated.

Executed Python: 3.13.9. Create a compatible virtual environment.
Install requirements-executed.txt, then `pip install --no-deps -e .`.
Run `python -m supplysignal.release --verify .` to check file integrity.
Run `python -m supplysignal.inference` to reproduce the sample forecasts.
Run `python -m supplysignal.train` to reproduce the fixed experiment.

The environment snapshot records installed versions; it is not a cross-platform lockfile.
Public-source attribution and snapshot hash are in data/processed/manifest.json.
Local packaging does not establish permission to redistribute third-party data publicly.
