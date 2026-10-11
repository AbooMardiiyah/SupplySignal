# Data provenance guide

**There is no real facility-level medicine stock history in this project.** Real public records provide facility context and a national/state survey benchmark. The monthly stock ledger and demo actions are synthetic or simulated.

The folders are arranged by processing stage (`raw`, `snapshots`, `processed`), not by whether every file is real or synthetic. Use this inventory to identify provenance.

## Real public data

| File | What it contains | How SupplySignal uses it |
|---|---|---|
| `snapshots/afijio_public_primary_arcgis.json` | Frozen public GRID3/NHFR facility registry extract: 47 public primary-facility records, of which 28 are PHCs | Facility identity, type, ward and coordinates for the demonstration map. It contains no stock reports. |
| `raw/afijio_public_primary_arcgis.json` | Downloaded version of the public registry extract | Input to the reproducible data pipeline. The app build copies the committed snapshot into this path. |
| `raw/nhfs_2023_results_tables.xlsx` | NBS National Health Facility Survey 2023 tables | The sources and data-cleaning notebook (Notebook 00) downloads and cleans the public workbook, saved under this filename. It uses national/state-level medicine availability for context only, not clinic-level labels. The download is not needed to run the app. |
| `snapshots/afijio_basemap.jpg`, `snapshots/afijio_basemap.json` | Attributed static street-map tiles and map bounds | Lets the app display the Afijio map offline. |

The full source description, query, date and checksum for the facility snapshot are in [`snapshots/README.md`](snapshots/README.md). Source URLs, cleaning checks and fingerprints are in notebook 00 and `../reports/analysis/source_fingerprints.csv`.

## Synthetic and fictional data

| File or input | Classification | Purpose |
|---|---|---|
| `processed/synthetic_lmis.csv` | **Synthetic** (2,016 rows; seed `20261004`) | Generated 24-month, 28-facility, three-product stock and reporting history. Used for model training, analysis and app worklists. It does not represent actual Nigerian inventory. |
| App demonstration counts and delivery events | **Simulated** | Seeded into the local operational store to exercise verification, transfer and escalation workflows. They are not facility-reported observations. |
| `example_lmis_input.csv`, `example_roster.csv`, `example_mapping.json` | **Fictional examples** | Small example files for the import-preview feature; their values are not field data. |

## Processed outputs

`processed/facilities.csv` is derived from the real public registry. Forecasts, model reports, predictions, action queues and ranking/workload reports in `processed/` are computed using the synthetic stock history alongside that facility context. The manifests record input provenance and simulator settings. In particular, `processed/` contains outputs based on both real facility context and synthetic inventory; its folder name describes processing stage, not data truth.

## Folder map

```text
data/
├── snapshots/   Versioned public inputs required by the offline app
├── raw/         Downloaded public source files (ignored by Git; regenerable)
├── processed/  Clean facility table plus generated synthetic ledger and results
├── interim/    Normalized import-preview output
└── example_*   Fictional CSV/JSON files for import preview
```

Large, restricted or personally sensitive data must not be committed. No patient-level data is used. See [`../docs/DATA_CARD.md`](../docs/DATA_CARD.md) for cleaning details, simulation assumptions and field definitions, and [`../notebooks/README.md`](../notebooks/README.md) for the analysis sequence.
