# Notebooks

Read or run them in order. Each one is saved with its outputs, so the results can be read on GitHub without running anything.

| Notebook | Question it answers |
|---|---|
| [00 · Sources, cleaning and real-data findings](00_sources_cleaning_and_real_data.ipynb) | What do we know about Afijio's PHCs, and what does national survey data say about medicine availability? |
| [01 · The simulated stock history](01_synthetic_reporting_and_stock_analysis.ipynb) | Is the simulation consistent, and what reporting problems does an officer face? |
| [02 · Demand forecasting experiment](02_demand_experiment.ipynb) | Does a model beat simple rules when it only sees reports that have arrived? |
| [03 · What makes an alert worth a call?](03_decision_utility_and_failure_analysis.ipynb) | Why do stock alerts raise false alarms, and how many calls are needed? |
| [04 · Model version and release](04_model_version_and_release.ipynb) | Which exact model is shipped, and does it reproduce after packaging? |

## Run them

From the project root, with Python 3.13:

```bash
pip install -c requirements-executed.txt -e '.[model,notebook]'
for nb in notebooks/0*.ipynb; do python scripts/execute_notebook.py "$nb"; done
```

Or open them in Jupyter or VS Code and run all cells in order. The sources and data-cleaning notebook (00) downloads and cleans the public NBS workbook, saved as `data/raw/nhfs_2023_results_tables.xlsx` (internet needed once). Notebook 01 generates the simulated stock ledger. Retraining in notebook 02 reproduces model version `demand-v1-965579aefe635327`.
