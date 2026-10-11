import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from supplysignal.decisions import create_queue, facility_call_plan, transferable_units
from supplysignal.pipeline import RAW
from supplysignal.train import DEFAULT_LEDGER


class DonorSafetyTest(unittest.TestCase):
    def test_plan_does_not_allocate_one_donors_surplus_multiple_times(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            facilities = root / "facilities.csv"
            ledger = root / "ledger.csv"
            records = [
                {"facility_id": key, "facility_name": key, "latitude": 7.7, "longitude": 3.9}
                for key in ("A", "B", "C", "D")
            ]
            reports = [
                {"facility_id": key, "commodity_id": "drug", "commodity_name": "Drug",
                 "period": "2026-09-01", "report_status": "reported", "submitted_at": "2026-10-02",
                 "consumption": 10, "closing_stock": 35 if key == "D" else 0,
                 "stockout_days": 0, "receipts": 0}
                for key in ("A", "B", "C", "D")
            ]
            def write(path, rows):
                with path.open("w", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=rows[0])
                    writer.writeheader()
                    writer.writerows(rows)
            write(facilities, records)
            events = [{"facility_id": row["facility_id"], "commodity_id": "drug",
                       "event_type": "stock_count", "event_date": "2026-10-04",
                       "units": row["closing_stock"]} for row in reports]
            def plan(rows):
                write(ledger, rows)
                return create_queue(date(2026, 10, 4), events=events, include_clear=True,
                                    forecast_strategy="three_report_mean", ledger_path=ledger,
                                    facilities_path=facilities)
            queue = plan(reports)
            self.assertEqual(queue, plan(list(reversed(reports))))
            transfers = [r for r in queue if r["action"] == "propose_transfer_for_verification"]
            self.assertEqual(sum(r["suggested_units"] for r in transfers), 15)
            self.assertTrue(all(r["donor_facility_id"] == "D" for r in transfers))
            partial = next(r for r in transfers if r["facility_id"] == "B")
            self.assertEqual(partial["suggested_units"], 5)
            self.assertEqual(partial["remaining_shortage_units"], 5)
            self.assertIn("Escalate", partial["next_step"])
            self.assertEqual(next(r for r in queue if r["facility_id"] == "C")["action"], "escalate_resupply")

    def test_queue_and_import_share_report_due_day(self):
        from supplysignal.import_preview import expected_report_period
        from supplysignal.reporting import latest_due_month

        for day, expected in ((9, "2026-08"), (10, "2026-09")):
            as_of = date(2026, 10, day)
            self.assertEqual(str(expected_report_period(as_of)), expected)
            self.assertEqual(latest_due_month(as_of).strftime("%Y-%m"), expected)
        self.assertEqual(latest_due_month(date(2026, 1, 9)), date(2025, 11, 1))
        self.assertEqual(latest_due_month(date(2026, 1, 10)), date(2025, 12, 1))

    def test_facility_call_plan_groups_products_without_losing_them(self):
        cases = [
            {"facility_id": "A", "facility_name": "PHC A", "commodity_name": "Drug 1", "action": "verify_stock", "signal": "Low reported cover"},
            {"facility_id": "B", "facility_name": "PHC B", "commodity_name": "Drug 2", "action": "verify_stock", "signal": "Forecast-only gap"},
            {"facility_id": "A", "facility_name": "PHC A", "commodity_name": "Drug 3", "action": "verify_stock", "signal": "Forecast-only gap"},
        ]
        calls = facility_call_plan(cases, capacity=1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["facility_id"], "A")
        self.assertEqual(calls[0]["products"], ["Drug 1", "Drug 3"])
        self.assertEqual(calls[0]["case_count"], 2)
        with self.assertRaises(ValueError):
            facility_call_plan(cases, capacity=0)

    def test_transfer_never_consumes_donor_reserve(self):
        self.assertEqual(transferable_units(35, 12), 11)
        self.assertEqual(transferable_units(24, 12), 0)
        self.assertEqual(transferable_units(5, 12), 0)

    @unittest.skipUnless(RAW.exists(), "Public facility extract has not been fetched")
    def test_unverified_reports_cannot_trigger_transfer_or_escalation(self):
        queue = create_queue()
        actions = {item["action"] for item in queue}
        self.assertIn("verify_stock", actions)
        self.assertNotIn("escalate_resupply", actions)
        self.assertNotIn("propose_transfer_for_verification", actions)
        self.assertTrue(all(item["data_provenance"] == "real facility; simulated inventory" for item in queue))

    @unittest.skipUnless(RAW.exists(), "Public facility extract has not been fetched")
    def test_recipient_then_donor_verification_unlocks_transfer(self):
        recipient = "0eceb876-3124-426a-ada6-525073e86e21"
        donor = "3ed1804e-6a9a-4a06-a51e-7256f7cddfbc"
        event = lambda facility, units, kind="stock_count": {
            "facility_id": facility, "commodity_id": "oxytocin", "event_type": kind,
            "units": units, "event_date": "2026-10-04", "expected_date": "2026-10-07",
        }
        def case(events):
            return next(row for row in create_queue(events=events, include_clear=True)
                        if row["facility_id"] == recipient and row["commodity_id"] == "oxytocin")

        self.assertEqual(case([])["action"], "verify_stock")
        self.assertEqual(case([event(recipient, 0)])["action"], "verify_donor")
        verified = case([event(recipient, 0), event(donor, 32)])
        self.assertEqual(verified["action"], "propose_transfer_for_verification")
        self.assertEqual(verified["suggested_units"], 2)
        self.assertEqual(verified["donor_facility_id"], donor)
        # A promised delivery does not add stock or suppress a genuine shortage.
        expected = case([event(recipient, 0), event(donor, 32), event(recipient, 20, "receipt_expected")])
        self.assertEqual(expected["action"], "propose_transfer_for_verification")
        self.assertEqual(expected["effective_stock"], 0)
        received = case([event(recipient, 0), event(donor, 32), event(recipient, 9, "receipt_confirmed")])
        self.assertEqual(received["action"], "no_action")
        self.assertEqual(received["effective_stock"], 9)

    @unittest.skipUnless(RAW.exists(), "Public facility extract has not been fetched")
    def test_worklist_distinguishes_reported_and_forecast_only_signals(self):
        queue = create_queue(include_clear=True)
        reported_zero = next(row for row in queue if row["action"] == "verify_stock" and row["effective_stock"] == 0)
        self.assertEqual(reported_zero["signal"], "Zero in last report")
        self.assertIn("confirm stock", reported_zero["next_step"])
        forecast_only = next(row for row in queue if row["signal"] == "Forecast-only gap")
        self.assertEqual(forecast_only["action"], "verify_stock")
        self.assertIn("not a confirmed shortage", forecast_only["next_step"])
        self.assertTrue(all(row["signal"] and row["next_step"] for row in queue))

    @unittest.skipUnless(DEFAULT_LEDGER.exists(), "Demo ledger not built")
    def test_receipt_score_cannot_see_late_submissions(self):
        as_of = date(2026, 7, 1)
        baseline = create_queue(
            as_of, priority_policy="receipt_gap", forecast_strategy="three_report_mean"
        )
        with DEFAULT_LEDGER.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        changed = 0
        for row in rows:
            if row["report_status"] == "reported" and row["submitted_at"] > as_of.isoformat():
                row["receipts"] = "99999"
                changed += 1
        self.assertGreater(changed, 0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "future_changed.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            after = create_queue(
                as_of, priority_policy="receipt_gap", forecast_strategy="three_report_mean",
                ledger_path=path,
            )
        self.assertEqual(
            [(row["facility_id"], row["commodity_id"], row["priority_score"]) for row in baseline],
            [(row["facility_id"], row["commodity_id"], row["priority_score"]) for row in after],
        )


if __name__ == "__main__":
    unittest.main()
