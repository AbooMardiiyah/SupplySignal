import unittest

from supplysignal.pipeline import RAW, load_facilities, simulate_ledger, validate_ledger


@unittest.skipUnless(RAW.exists(), "Public facility extract has not been fetched")
class PipelineTest(unittest.TestCase):
    def test_registry_keys_and_stock_ledger(self):
        facilities = load_facilities()
        self.assertEqual(len(facilities), 28)
        self.assertEqual(len({facility["facility_id"] for facility in facilities}), 28)
        ledger = simulate_ledger(facilities)
        validate_ledger(ledger, len(facilities))
        self.assertTrue(any(row["report_status"] == "missing" for row in ledger))
        self.assertTrue(any(int(row["truth_unmet_units"]) > 0 for row in ledger))
        for row in ledger:
            if row["report_status"] == "missing":
                self.assertEqual(row["consumption"], "")
                self.assertEqual(row["closing_stock"], "")


if __name__ == "__main__":
    unittest.main()
