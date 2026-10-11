# Data card

## Datasets

| Dataset | Size | Real or simulated | Used for |
|---|---|---|---|
| Afijio registry extract (GRID3/NHFR) | 47 records → 28 public PHCs | **Real** | Facility names, wards and coordinates |
| NBS National Health Facility Survey 2023 | State-level tables | **Real** | Context, such as essential-medicine availability; never used as clinic labels |
| Monthly stock ledger | 28 PHCs × 3 products × 24 months = 2,016 rows | **Simulated** (seed 20261004) | Demo, model experiments and decision analysis |
| Officer observations | Entered in the app | **Simulated demo inputs** | Scripted counts, deliveries and follow-ups to exercise the prototype; not field observations |
| Example LMIS import | 3 monthly rows plus a roster | Fictional | Import preview |

Source links, checksums and extraction steps are in notebook 00 and `reports/analysis/source_fingerprints.csv`. The frozen registry and basemap are described in `data/snapshots/README.md`.

## Cleaning

The registry was filtered to the public PHC subtype. Coordinates were bounds-checked, and missing or duplicated NHFR codes were audited (15 missing; one code shared by two records). Keys were made unique per facility, product and month. Quantities are numeric and non-negative with explicit units. Stock-balance discrepancies are kept for investigation rather than overwritten, and unknown values are never filled with zero. No patient-level data is used.

## Stock ledger fields

| Field | Meaning |
|---|---|
| `facility_id`, `commodity_id`, `period` | Series key: facility × product × month |
| `opening_stock`, `receipts`, `consumption`, `losses`, `adjustments`, `closing_stock` | Monthly accounting; closing = opening + receipts − consumption − losses + adjustments |
| `stockout_days` | Days out of stock in the month |
| `report_status`, `submitted_at` | Whether the report arrived, and when; late reports are invisible to earlier forecasts |
| `truth_latent_demand`, `truth_unmet_units` | Hidden simulated truth, used **only** for evaluation; never a model input |

## Model features

| Feature | Construction |
|---|---|
| `last_consumption`, `mean_3_consumption`, `mean_6_consumption`, `std_3_consumption` | From reports submitted before the forecast date |
| `report_age_months`, `visible_reports_last_3`, `visible_reports_last_6` | How fresh and complete the reporting is |
| `month_sin`, `month_cos`, `commodity__*` | Calendar position and product |
| `label_consumption` | Target-month dispensing; fitted only when uncensored (submitted, no stockout days, positive closing stock) and submitted before the training cut-off |

## Simulation settings

| Mechanism | Setting |
|---|---|
| Base monthly demand | Oxytocin 12, magnesium sulfate 5, misoprostol 18, scaled by a facility multiplier of 0.55–1.7 |
| Seasonality and noise | ×1.15 in June–September; ±30% monthly noise |
| Resupply | When stock falls below twice monthly demand; 10% chance a delivery does not arrive |
| Reporting | About 4.5% of reports missing; delays of 2–29 days, with an 8% chance of a further month |
| Demo scenarios | Scripted late shortages, a silent clinic and a donor surplus, to exercise every app path |

## Scope

One LGA, one facility type, three maternal medicines and 24 months. A real deployment uses the LGA's own LMIS export and an agreed facility and product crosswalk (see [REAL_DATA_CONTRACT.md](REAL_DATA_CONTRACT.md)).
