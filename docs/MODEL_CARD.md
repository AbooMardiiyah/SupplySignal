# Model card: monthly demand model

| | |
|---|---|
| **Version** | `demand-v1-965579aefe635327` (checksums in `reports/model_release.json`) |
| **Task** | Forecast next-month consumption for each facility × product, as one input to the verification worklist |
| **Model** | LightGBM, Poisson loss, 180 trees, learning rate 0.05, 15 leaves, min 20 child samples, seed 42 |
| **Training data** | Simulated monthly stock ledger for 28 Afijio PHCs and 3 maternal medicines (see [DATA_CARD.md](DATA_CARD.md)) |

## Intended use

Estimate expected demand so the worklist can flag clinics whose reported stock may not last four weeks. Every flag leads to a **verification call**, never an automatic stock movement. It is not used for treatment decisions or patient-level prediction.

## Inputs

Only reports submitted before the forecast date: last consumption, three- and six-report means and variability, report age, number of recent reports, calendar position and product. Facility names, coordinates and the simulator's hidden truth are never inputs.

## Training and selection

- **Labels:** consumption from months with a submitted report, zero stockout days and positive closing stock, so months where stock ran out (and demand was hidden) are excluded.
- **Chronological split:** train on target months April 2025–February 2026, validate on March–May 2026, test on June–September 2026. Labels must have arrived before each cut-off.
- **Candidates:** last report, three-report mean, histogram gradient boosting and LightGBM; the lowest validation MAE was selected.
- **Not evaluated:** Prophet, seasonal naïve/SARIMA, and LSTM or other sequence models. The selection claim applies only to the candidates above. A future comparison should use the same point-in-time inputs and chronological splits on authorised facility data; LSTM should be considered only if the available history is large and consistent enough.
- **Robustness:** seven expanding time origins and feature ablations (notebook 02).

## Results (simulated test months, 336 rows)

| Model | WAPE |
|---|---:|
| **LightGBM (selected)** | **16.7%** |
| Three-report mean | 18.9% |

**How to read these metrics:** WAPE is the sum of absolute forecast errors divided by total actual demand. In everyday terms, 16.7% means about 17 units of total forecast miss for every 100 units actually used across the test rows. The validation metric, MAE, is the average absolute miss in units per facility-product-month; the lowest validation MAE selected the candidate. The 12% relative reduction compares 16.7% with 18.9%; it does not mean 12% fewer stockouts.

Mean bias is −0.33 units. The decision analysis (notebook 03) shows that the main driver of false alarms is stale stock information rather than forecast error, which is why every flag starts with a verification call.

## Explainability and uncertainty

- **SHAP** (exact TreeSHAP from LightGBM): the six-report average consumption drives the forecast, followed by the three-report average and calendar month. Officers see plain-language reasons in the app instead.
- **Forecast ranges:** quantile LightGBM models (P10, P50, P90), calibrated with split conformal prediction on the validation months. P10–P90 coverage on the test months: 63.7% raw, **78.0% calibrated** (target 80%; 150 calibration labels available by the first test forecast date). A more cautious P90 alert adds false alarms without catching more shortages, the ranges remain a notebook experiment. The app and saved point-model release do not use conformal ranges to size donor reserves. Coverage is empirical under this simulation; temporal dependence and distribution shift preclude a general 80% coverage guarantee.

## Missing and new data

Tree models handle missing history directly; baselines fall back to the training median. Clinics that never report are surfaced through the expected roster, not through the model.

## Deployment path

For a real LGA, the import worklist runs on transparent rules first. The proposed pilot would retrain on the LGA's own history once enough uncensored months exist, and monitor for data freshness, failed imports, disagreement with verified counts and missed shortages.

## Reproducibility

The release records dataset and code SHA-256 hashes, parameters, the feature schema, dependency versions and model bytes, and reproduces predictions exactly after reload (84-row parity check). Retraining from a clean checkout reproduces the same version ID. Recorded environment: Python 3.13.9.
