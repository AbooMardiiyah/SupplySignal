import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from supplysignal.import_preview import expected_report_period, preview_worklist
from supplysignal.ingest import normalize


ROOT = Path(__file__).resolve().parents[1]


class ImportPreviewTest(unittest.TestCase):
    def test_fictional_example_catches_low_stock_and_never_reported_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "normalized.csv"
            normalize(
                ROOT / "data/example_lmis_input.csv", output,
                ROOT / "data/example_mapping.json",
            )
            reports = pd.read_csv(output)
            roster = pd.read_csv(ROOT / "data/example_roster.csv", dtype=str)
            work = preview_worklist(reports, roster, date(2026, 10, 4))
            self.assertEqual(len(work), 2)
            self.assertEqual(work.iloc[0]["signal"], "Never reported")
            self.assertEqual(work.iloc[1]["signal"], "Low reported cover")
            self.assertEqual(work.iloc[1]["monthly_consumption_baseline"], 29.666666666666668)

    def test_late_submission_is_not_visible_and_due_month_changes_on_day_ten(self):
        reports = pd.DataFrame([{
            "facility_id": "PHC-1", "commodity_id": "OXY",
            "period": "2026-08-01", "submitted_at": "2026-10-05",
            "closing_stock": 0, "consumption": 10,
        }])
        roster = pd.DataFrame([{"facility_id": "PHC-1", "commodity_id": "OXY"}])
        work = preview_worklist(reports, roster, date(2026, 10, 4))
        self.assertEqual(work.iloc[0]["signal"], "Never reported")
        self.assertEqual(str(expected_report_period(date(2026, 10, 4))), "2026-08")
        self.assertEqual(str(expected_report_period(date(2026, 10, 10))), "2026-09")

    def test_duplicate_roster_rejected(self):
        roster = pd.DataFrame([
            {"facility_id": "PHC-1", "commodity_id": "OXY"},
            {"facility_id": "PHC-1", "commodity_id": "OXY"},
        ])
        reports = pd.DataFrame(columns=[
            "facility_id", "commodity_id", "period", "submitted_at", "closing_stock", "consumption",
        ])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            preview_worklist(reports, roster, date(2026, 10, 4))

    def test_empty_roster_rejected(self):
        roster = pd.DataFrame(columns=["facility_id", "commodity_id"])
        reports = pd.DataFrame(columns=[
            "facility_id", "commodity_id", "period", "submitted_at", "closing_stock", "consumption",
        ])
        with self.assertRaisesRegex(ValueError, "no facility-product pairs"):
            preview_worklist(reports, roster, date(2026, 10, 4))


if __name__ == "__main__":
    unittest.main()
