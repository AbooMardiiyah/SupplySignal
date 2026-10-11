# Verification — 9 October 2026

| Check | Result | Evidence |
|---|---|---|
| Unit tests | 33 passed | [verification/unit-tests.log](verification/unit-tests.log) |
| Browser workflow (Playwright, external requests blocked) | 15 checks passed | [verification/browser-smoke.log](verification/browser-smoke.log) |
| Lint (E9, F63, F7, F82) | Passed across `src`, `app`, `scripts` and `tests` | `ruff check --select E9,F63,F7,F82` |
| Fresh Docker build | Passed; the built image alone serves the offline map (28 PHCs) and ten call cards with external requests blocked | `docker build .` |
| Executed notebooks | Five notebooks with saved outputs and charts | [notebooks/](../notebooks/README.md) |
| Model release | `demand-v1-965579aefe635327`: 30 files checksum-verified; exact prediction parity on 84 rows after reload | [model_release.json](model_release.json) |

## Browser checks

1. The map renders offline with all 28 PHCs and ten call cards.
2. The offline call worksheet has ten facility calls, 24 product checks and explicit unknowns.
3. The CSV download produces 52 readable backlog rows.
4. The displayed-case export follows the ten-case filter.
5. A call card opens the clinic on the Verify and update tab.
6. The fictional LMIS import exposes low cover and a roster pair that never reported.
7. An uploaded LMIS CSV, roster and field mapping produce a worklist.
8. A follow-up is saved without changing the supply alert.
9. A recipient count promotes the case to donor verification.
10. A donor count unlocks a conditional transfer proposal showing the proposed units.
11. An expected delivery does not add stock.
12. A confirmed delivery changes stock and clears the shortage.
13. A duplicate receipt is rejected.
14. The decision persists after a page refresh.
15. A verified shortage without a donor escalates for resupply.

The browser test runs against a disposable container, never the observation volume of the review app.

## Submission review — 10 October 2026

- Re-ran all 33 unit tests and the critical lint gate: passed. The application
  code was not changed during this review; the 15 browser checks above are
  the earlier completed run, not a newly claimed run.
- Inspected all five saved notebooks: 47 code cells, all executed, no error
  outputs. Re-executed notebooks 02 and 03 after the corrections below.
- Corrected conformal calibration to include only labels submitted by the
  first test forecast date. This excludes 83 late labels (150 remain).
  Observed test coverage is 63.7% raw and 78.0% calibrated, against an 80%
  target. These experimental ranges are not deployed in the app.
- Relabelled the information diagnostic as hindsight: true month-opening
  stock and all target-month receipts are not all available at forecast time.
  The 201 → 49 → 1 result is not a measured live false-alarm reduction.
- Re-verified all 30 checksummed files in model release
  `demand-v1-965579aefe635327`; the selected point model is unchanged.
- Checked the final supplied video: 4:41.79, 1920×1080, H.264 video and AAC
  audio. A separate reviewed copy adds one context label over the experiment
  section while preserving the YarnGPT audio. No narration was regenerated.
- Removed submission-link placeholders from the written assets; links belong
  in the Google Form and can be added to the README once available.
