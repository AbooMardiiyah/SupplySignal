# PHC SupplySignal

**When stock reports are late or missing, the report alone is not enough. SupplySignal helps LGA officers find which clinics to call, verify what is actually on the shelf, and decide what to do next.**

Decision support for primary healthcare supply officers, demonstrated with 28 public PHCs in Afijio LGA, Oyo State.

## Submission materials

- **Demo video:** [Watch the demo](https://youtu.be/OZvl_OSMQdk).
- **One-page write-up:** [View the PDF](https://drive.google.com/file/d/1FA2nIT5f_OW0TeNWtGvKSTZ7hFwySjsv/view?usp=sharing).
- **Data sources and synthetic-data disclosure:** [Data provenance guide](data/README.md) · [Full data card](docs/DATA_CARD.md).

Submit this repository URL: https://github.com/AbooMardiiyah/SupplySignal.

## The problem

Primary healthcare centres are often the first point of care, but reports about medicine availability can arrive late, incompletely, or not at all. That leaves LGA supply officers making restocking decisions with an outdated picture of clinic shelves.

Nigeria's 2023 National Health Facility Survey found essential-medicine availability averaging about 34% in public PHCs. A monthly report cannot show a delivery or stock change that happened after it was submitted.

## Our insight

We first built the expected solution: forecast demand and flag stockout risk. On simulated history, LightGBM lowered forecast error by about 12% against a three-report average. But stock alerts based on old information raised many false alarms. In a retrospective simulation, fresher stock information reduced false alarms from 201 to 49; using full-month receipts reduced them to 1 while retaining 10 shortages. The full-month receipts include hindsight, so this is a diagnostic—not a live-impact claim.

**That changed the product:** SupplySignal makes verification the first action. It helps an officer find the calls most likely to change a decision, record what the clinic confirms, and then show the next step.

![False alarms fall as stock information gets fresher](docs/images/false_alarms.png)

## What the officer does

1. **Prioritize calls.** A map and worklist flag missing, late, zero or low reports and forecast gaps. One call checks several medicines at the same clinic.
2. **Verify the shelf.** Record a physical count and follow-up. A stale report saying 164 units can be corrected when the clinic confirms 40.
3. **Choose a safe next step.** SupplySignal can propose a transfer from a nearby clinic while protecting the donor's reserve, or escalate the remaining need. A promised delivery is not treated as stock, duplicate receipts are rejected, and actions are logged.

![SupplySignal worklist map](docs/images/worklist_map.jpg)

In the demo, Abujakan's oxytocin count is zero. Fiditi's report says 164 units, but its verified count is 40. SupplySignal proposes 12 units for Abujakan and escalates the remaining 8.

## What makes it different

- **Verification before escalation:** a risk flag is a reason to check, not a claim that a stockout has happened.
- **Designed for reporting gaps:** the worklist can include facilities that did not report, using the expected facility-product roster.
- **Constrained transfer suggestions:** donor reserves and shared surplus are checked before proposing a transfer; unresolved need remains visible.
- **Works with low connectivity:** after installation it runs locally, and the call sheet can support paper-based follow-up.
- **Fits existing systems:** an NHLMIS or DHIS2 export and facility roster can be previewed; SupplySignal is not a replacement for those systems.

## Data: what is real and what is synthetic?

The project folders are arranged by processing stage, so provenance is called out here rather than inferred from a folder name.

| Data | Classification | Files and use |
|---|---|---|
| Facility names, types, wards and coordinates | **Real, public** | `data/snapshots/afijio_public_primary_arcgis.json`; cleaned to `data/processed/facilities.csv`. Identifies the 28 demonstration PHCs; contains no medicine-stock observations. |
| National Health Facility Survey 2023 tables | **Real, public** | The sources and data-cleaning notebook (Notebook 00) downloads the NBS workbook and saves it as `data/raw/nhfs_2023_results_tables.xlsx`. It is used for national/state context, not clinic-level labels; the raw download is not needed to run the app. |
| Monthly facility-product stock reports | **Synthetic** | `data/processed/synthetic_lmis.csv` (2,016 rows, fixed seed). Used for the demo, model experiments and decision analysis. These are not Nigerian facility observations. |
| Import examples | **Fictional** | `data/example_lmis_input.csv`, `data/example_roster.csv` and `data/example_mapping.json`; used only to demonstrate the import preview. |
| Demo counts and delivery events | **Simulated demonstration inputs** | Seeded in the local app's operational store to make the walkthrough reproducible; they are not field observations. |

See [data/README.md](data/README.md) for a file-by-file guide and [docs/DATA_CARD.md](docs/DATA_CARD.md) for cleaning, simulation assumptions and field definitions. The five executed notebooks show the full path from public sources and data checks to synthetic-data experiments and the released model.

## Evidence and current limits

- Five notebooks run in order and save their outputs; notebook 00 examines the real registry and survey context, while later notebooks clearly label simulated stock history.
- On the simulated test period, LightGBM's WAPE was 16.7%, compared with 18.9% for a three-report mean. WAPE is the total absolute forecast error divided by total actual demand: roughly, how many units the forecasts missed by for every 100 units actually used. This is about 12% lower relative error, not 12% fewer stockouts. Prophet, SARIMA and LSTM were not tested.
- The import screen validates and previews an upload but does not yet save an imported LGA workspace. No LGA pilot or institutional partnership has been secured.
- The next step is a proposed four-week pilot with an LGA, using authorized stock exports and a facility roster. The evaluation would measure time to current stock evidence, shortages found per ten calls, and officer time.

## Run the prototype

Requires Docker. From the repository root:

```bash
make up       # build and start in the background
```

Open [http://localhost:8501](http://localhost:8501). To stop the app while keeping saved demo observations:

```bash
make down
```

The app runs locally after the initial image build. Try the video scenario by recording zero misoprostol and zero oxytocin for Abujakan, then a verified count of 40 oxytocin units for Fiditi. Return to Abujakan to see the transfer proposal and remaining escalation.

## Repository guide

| Path | Contents |
|---|---|
| `app/` | Streamlit prototype: worklist, verification, follow-up and import preview |
| `src/supplysignal/` | Data pipeline, model, ranking, decisions and operational records |
| `notebooks/` | Five executed notebooks covering real sources, synthetic data, experiments and model release |
| `data/` | Public snapshots, clearly named synthetic ledger and fictional import examples |
| `artifacts/` | Trained model and checksummed release |
| `docs/` | Submission write-up, model/data cards, pilot plan and import contract |
| `reports/` | PDF write-up, verification results and reviewed demo video |
| `tests/` | Unit and browser workflow checks |

For development commands, run `make help`. The model selection and limitations are documented in the [model card](docs/MODEL_CARD.md); see [notebooks/README.md](notebooks/README.md) to read or rerun the analysis.
