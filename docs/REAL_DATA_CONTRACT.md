# Bring your own data: LMIS import format

The importer accepts a **long-format monthly report**: one row per
facility, commodity (including formulation and strength), and calendar month.
This is a normalized interchange table, not a claim that every Nigerian DHIS2
installation exports exactly these column names. Use `--mapping` to rename
source columns; wide programme-specific exports first need reshaping.

DHIS2's [monthly stock reporting guide](https://docs.dhis2.org/cs/implement/logistics/monthly-stock-reporting-msr.html)
describes stock on hand, consumption, receipts, redistribution, discard and
stockout duration. The same concepts underlie this contract.

| Field | Meaning | Required to import? |
|---|---|---|
| `facility_id` | Stable facility/organisation-unit code | Yes |
| `commodity_id` | Stable code for exact product, strength and form | Yes |
| `period` | Month being reported, e.g. `2026-08-01` | Yes |
| `unit` | Count unit such as ampoule or tablet; never mix pack sizes | Yes |
| `consumption` | Units issued/dispensed during month | Yes |
| `closing_stock` | Physical end-month count in the same unit | Yes |
| `submitted_at` | Date report reached the system, in WAT | Yes |
| `opening_stock`, `receipts`, `losses`, `adjustments` | Stock ledger movements | Optional; needed to audit balance |
| `stockout_days` | Days unavailable during the month, 0 to month length | Strongly recommended; needed for uncensored demand labels |
| `batch_expiry` | Earliest relevant expiry, if single-batch | Optional; a lot-level table is preferable |
| `source` | Programme/system and extract version | Optional |

The importer checks unique keys, dates, consistent product units, nonnegative counts and month
lengths. It keeps any discrepancy between physical closing stock and computed
balance for investigation. A missing report is an **absent row**; it is never
converted to a zero stock balance. An expected-reporting roster must include
all facility-product pairs so a facility that has never reported is still
visible at inference.

`example_lmis_input.csv` and `example_mapping.json` show the file format. They
contain fictional numbers and are not Nigerian observations.

## Training labels and operational reality

The model learns monthly demand from reported consumption only when the
facility reported zero stockout days and had positive closing stock. Dispensed
quantity during a stockout is censored; it understates need. If real
`stockout_days` is absent, the training job refuses to invent uncensored labels.
More complete demand estimation would need service volume, prescriptions or
unfilled requests linked by facility and time.

Forecasting also needs reports soon enough to act. The current simulation
shows that a four-week alert made on the first of a month usually lacks the
previous month's stock count. A field pilot should measure report delay,
delivery status and physical-count verification. Forecast quality alone is
insufficient to establish useful stockout alerts.

## Example commands

```bash
PYTHONPATH=src python3 -m supplysignal.ingest \
  --input data/example_lmis_input.csv \
  --mapping data/example_mapping.json \
  --output data/interim/normalized_example.csv

PYTHONPATH=src python3 -m supplysignal.inference \
  --ledger data/interim/authorized_lmis.csv \
  --roster data/authorized_roster.csv \
  --artifact artifacts/authorized_model.joblib \
  --target-period 2026-10-01 --as-of 2026-10-04
```

The default train/validation/test dates suit the 24-month demonstration.
For a real extract, choose calendar cutoffs based on its actual coverage and
freeze them for the experiment. The training CLI accepts `--first-target`,
`--train-end`, `--validation-end` and `--test-end`; the dates must be ordered.
The importer validates shape and units, but it cannot establish whether an
LMIS report is accurate. Reconcile physical counts and confirm product codes
with the LGA before using recommendations operationally.
