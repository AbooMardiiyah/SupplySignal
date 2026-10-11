import tempfile
import unittest
from datetime import date
from pathlib import Path

from supplysignal.operations import (
    list_case_events, list_events, record_case_event, record_event,
)


class ObservationStoreTest(unittest.TestCase):
    def test_follow_up_trail_is_separate_from_inventory_and_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "observations.sqlite3"
            self.assertEqual(list_case_events(db), [])
            record_event(
                "PHC-1", "OXY-10IU", "stock_count", 0, date(2026, 10, 4),
                recorded_by="Officer", db_path=db,
            )
            self.assertEqual(list_case_events(db), [])
            with self.assertRaisesRegex(ValueError, "note is required"):
                record_case_event(
                    "PHC-1", "OXY-10IU", "contact_attempted", date(2026, 10, 4),
                    note="", recorded_by="Officer", db_path=db,
                )
            case_id = record_case_event(
                "PHC-1", "OXY-10IU", "facility_unreachable", date(2026, 10, 4),
                note="Phone unanswered", recorded_by="Officer", db_path=db,
                as_of=date(2026, 10, 4),
            )
            self.assertEqual(case_id, 1)
            self.assertEqual(list_case_events(db)[0]["note"], "Phone unanswered")
            self.assertEqual(len(list_events(db)), 1)
            with self.assertRaisesRegex(ValueError, "Backdated"):
                record_case_event(
                    "PHC-1", "OXY-10IU", "contact_attempted", date(2026, 10, 3),
                    note="Earlier attempt", recorded_by="Officer", db_path=db,
                )
            self.assertEqual(len(list_case_events(db)), 1)

    def test_follow_up_can_be_first_event_in_new_database(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "observations.sqlite3"
            record_case_event(
                "PHC-1", "OXY-10IU", "contact_attempted", date(2026, 10, 4),
                note="Called twice", recorded_by="Officer", db_path=db,
            )
            self.assertEqual(list_events(db), [])
            self.assertEqual(len(list_case_events(db)), 1)

    def test_append_only_log_persists_and_rejects_backdating(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "observations.sqlite3"
            self.assertEqual(list_events(db), [])
            event_id = record_event(
                "PHC-1", "OXY-10IU", "stock_count", 0, date(2026, 10, 4),
                recorded_by="LGA officer", db_path=db, as_of=date(2026, 10, 4),
            )
            self.assertEqual(event_id, 1)
            self.assertEqual(list_events(db)[0]["units"], 0)
            self.assertEqual(list_events(db)[0]["recorded_by"], "LGA officer")
            with self.assertRaisesRegex(ValueError, "Backdated"):
                record_event(
                    "PHC-1", "OXY-10IU", "stock_count", 5, date(2026, 10, 3),
                    recorded_by="LGA officer", db_path=db,
                )
            self.assertEqual(len(list_events(db)), 1)

    def test_expected_and_confirmed_receipts_need_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "observations.sqlite3"
            with self.assertRaisesRegex(ValueError, "arrival date"):
                record_event(
                    "PHC-1", "OXY-10IU", "receipt_expected", 12, date(2026, 10, 4),
                    recorded_by="LGA officer", db_path=db,
                )
            with self.assertRaisesRegex(ValueError, "delivery reference"):
                record_event(
                    "PHC-1", "OXY-10IU", "receipt_confirmed", 12, date(2026, 10, 4),
                    recorded_by="LGA officer", db_path=db,
                )
            self.assertEqual(list_events(db), [])

    def test_confirmed_delivery_reference_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "observations.sqlite3"
            arguments = dict(
                facility_id="PHC-1", commodity_id="OXY-10IU", event_type="receipt_confirmed",
                units=12, event_date=date(2026, 10, 4), reference="WAYBILL-123",
                recorded_by="LGA officer", db_path=db,
            )
            record_event(**arguments)
            with self.assertRaisesRegex(ValueError, "already recorded"):
                record_event(**arguments)
            self.assertEqual(len(list_events(db)), 1)


if __name__ == "__main__":
    unittest.main()
