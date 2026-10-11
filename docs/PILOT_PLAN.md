# Path to impact: fit and pilot plan

## Where SupplySignal fits

Nigeria already collects stock data through NHLMIS, which is linked to DHIS2. DHIS2 and OpenLMIS support stock counts, receipts and offline capture. SupplySignal does not replace any of them. It works on their exports and adds the step that turns late or missing reports into a short list of verification calls, then turns each verified answer into a conditional next action.

| Operating constraint | How the prototype responds |
|---|---|
| Unreliable power and internet | Runs on a local computer with a stored map; saved observations survive restarts; a printable call sheet allows work on paper |
| Limited officer time | One call checks every flagged medicine at a clinic; ten calls cover 24 product checks in the demo |
| Inconsistent identifiers and units | Imports are validated for units, dates and stock balance before any worklist is built |
| Limited supply | Transfers protect the donor's reserve and share surplus across all requests; unmet need is escalated, not hidden |
| Accountability | Every observation records who entered it and when; duplicate receipts are rejected; no patient data is collected |

## Four-week pilot

**Proposed partner (not yet secured):** one LGA logistics or pharmacy officer, with PHC storekeepers confirming counts and the existing supply authority approving any action.

**Planned first slice:** authorised monthly export plus the expected clinic roster → validation → verification worklist → recorded counts → next actions. Transparent rules come first; the demand model is trained once the LGA's own history is available.

| Period | Work | Evidence collected |
|---|---|---|
| Before start | Agree permissions, facility and product identifiers, units and eligibility; record current practice as the baseline | Approved cohort and data fields |
| Week 1 | Observe the current workflow and validate an authorised extract | Time per task, reporting completeness, identifier match rate, balance discrepancies |
| Weeks 2–3 | Run the worklist alongside current practice | Calls made, counts recovered, unreachable clinics, time to current stock evidence |
| Week 4 | Check a sample of clinics outside the worklist and reconcile actions with evidence | Shortages found and missed, unresolved unknowns, usability feedback |

The current import feature stops at a session-only verification preview. Saving
imported cohorts, dated observations and reconciled follow-up is the next implementation step.

## What we measure

- **Speed:** time from alert to a current stock count; products checked per call.
- **Effectiveness:** verified shortages found per ten calls, compared with current practice; shortages missed in the outside-list sample.
- **Safety:** no action from unverified counts, no donor reserve breached, no promised delivery counted as stock.
- **Burden:** officer and storekeeper minutes, and duplicate-entry steps.
- **Outcome (longer term):** stockout days for oxytocin, misoprostol and magnesium sulfate where longitudinal data exists.

## Settings to confirm with the partner

The demo uses a seven-day validity for counts, a two-month donor reserve and a 75 km straight-line donor radius. Product specifications, clinic eligibility, route times and expiry rules are set with the partner before go-live.
