import tempfile
import unittest
from pathlib import Path

from supplysignal.ranking_eval import run
from supplysignal.train import DEFAULT_ARTIFACT, DEFAULT_LEDGER


@unittest.skipUnless(DEFAULT_ARTIFACT.exists() and DEFAULT_LEDGER.exists(), "Demo model and ledger not built")
class RankingGateTest(unittest.TestCase):
    def test_failed_validation_cannot_replace_deployed_order(self):
        with tempfile.TemporaryDirectory() as directory:
            report = run(report_path=Path(directory) / "ranking.json")
        self.assertEqual(report["selected_policy"], "coverage_gap")
        self.assertFalse(report["deployment_gate"]["candidate_accepted"])
        self.assertEqual(report["deployment_gate"]["deployed_policy"], "absolute_gap")
        self.assertFalse(report["deployment_gate"]["worklist_validated_for_field_use"])
        self.assertEqual(report["development"]["coverage_gap"]["forecast_strategy"], "three_report_mean")
        self.assertEqual(report["validation_untouched_during_selection"]["coverage_gap"]["top_k_hits"], 1)
        self.assertEqual(report["exploratory_test_already_inspected"]["absolute_gap"]["top_k_hits"], 2)
        stress = report["receipt_challenger_stress_test"]
        self.assertEqual(len(stress["by_seed"]), 6)
        self.assertEqual(stress["top_10_product_hits"], {"absolute_gap": 4, "receipt_gap": 6})
        self.assertLess(stress["top_10_unmet_units"]["receipt_gap"], stress["top_10_unmet_units"]["absolute_gap"])
        for metrics in report["validation_untouched_during_selection"].values():
            self.assertLessEqual(metrics["facility_call_hits"], metrics["facility_calls"])
            self.assertGreaterEqual(metrics["flagged_products_at_called_facilities"], metrics["facility_calls"])


if __name__ == "__main__":
    unittest.main()
