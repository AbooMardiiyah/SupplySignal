import tempfile
import unittest
from pathlib import Path

import pandas as pd

from supplysignal.features import prepare_ledger, snapshot_features
from supplysignal.ingest import normalize
from supplysignal.inference import predict
from supplysignal.train import DEFAULT_ARTIFACT, DEFAULT_LEDGER


class IngestTest(unittest.TestCase):
    def test_example_mapping_and_balance(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "normalized.csv"
            summary = normalize(root / "data/example_lmis_input.csv", output, root / "data/example_mapping.json")
            result = pd.read_csv(output)
            self.assertEqual(summary["rows"], 3)
            self.assertEqual(summary["balance_discrepancies"], 0)
            self.assertEqual(set(result["provenance"]), {"observed"})

    def test_mixed_units_rejected(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            source = pd.read_csv(root / "data/example_lmis_input.csv")
            source.loc[1, "stock_unit"] = "pack"
            input_path = Path(directory) / "mixed.csv"
            source.to_csv(input_path, index=False)
            with self.assertRaisesRegex(ValueError, "multiple stock units"):
                normalize(input_path, Path(directory) / "out.csv", root / "data/example_mapping.json")

    def test_unrelated_personal_column_is_not_propagated(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            source = pd.read_csv(root / "data/example_lmis_input.csv")
            source["patient_name"] = "Do not retain"
            input_path = Path(directory) / "with_extra.csv"
            output_path = Path(directory) / "normalized.csv"
            source.to_csv(input_path, index=False)
            normalize(input_path, output_path, root / "data/example_mapping.json")
            self.assertNotIn("patient_name", pd.read_csv(output_path).columns)


class FeatureTest(unittest.TestCase):
    def test_late_report_is_invisible_until_submission(self):
        ledger = prepare_ledger(pd.DataFrame([
            {"facility_id": "A", "commodity_id": "P", "period": "2026-07-01", "consumption": 10,
             "closing_stock": 30, "submitted_at": "2026-08-02", "report_status": "reported", "stockout_days": 0},
            {"facility_id": "A", "commodity_id": "P", "period": "2026-08-01", "consumption": 20,
             "closing_stock": 10, "submitted_at": "2026-09-10", "report_status": "reported", "stockout_days": 0},
        ]))
        early = snapshot_features(ledger, "2026-09-01", "2026-09-01").iloc[0]
        late = snapshot_features(ledger, "2026-09-01", "2026-09-11").iloc[0]
        self.assertEqual(early["last_consumption"], 10)
        self.assertEqual(early["report_age_months"], 2)
        self.assertEqual(late["last_consumption"], 20)
        self.assertEqual(late["report_age_months"], 1)

    @unittest.skipUnless(DEFAULT_ARTIFACT.exists() and DEFAULT_LEDGER.exists(), "Model artifact not built")
    def test_inference_includes_never_reporting_roster_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            roster = Path(directory) / "roster.csv"
            pd.DataFrame([{"facility_id": "NEVER-REPORTED", "commodity_id": "oxytocin"}]).to_csv(roster, index=False)
            result = predict(DEFAULT_LEDGER, DEFAULT_ARTIFACT, "2026-10-01", "2026-10-04", roster)
            self.assertEqual(len(result), 1)
            self.assertTrue(bool(result.iloc[0]["requires_verification"]))
            self.assertGreaterEqual(result.iloc[0]["forecast_demand_units"], 0)


if __name__ == "__main__":
    unittest.main()
