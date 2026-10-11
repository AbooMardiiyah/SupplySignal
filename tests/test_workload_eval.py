import unittest

from supplysignal.workload_eval import order_cases, score_calls


def case(facility: str, product: str, stock, period: str) -> dict:
    return {
        "facility_id": facility,
        "facility_name": facility,
        "commodity_id": product,
        "commodity_name": product,
        "action": "verify_stock",
        "signal": "Low reported cover",
        "stock_on_last_report": stock,
        "last_report_period": period,
    }


class WorkloadEvaluationTest(unittest.TestCase):
    def test_shortage_in_unflagged_product_is_missed_even_when_facility_called(self):
        cases = [case("A", "oxytocin", 0, "2026-08-01"), case("B", "oxytocin", 4, "2026-08-01")]
        outcomes = {("A", "oxytocin"): 0, ("A", "misoprostol"): 8, ("B", "oxytocin"): 3}
        metrics = score_calls(cases, outcomes, capacity=1)
        self.assertEqual(metrics["facility_calls"], 1)
        self.assertEqual(metrics["shortage_calls"], 0)
        self.assertEqual(metrics["missed_shortage_products"], 2)
        self.assertEqual(metrics["unmet_units_found"], 0)

    def test_multi_product_call_counts_one_call_and_two_checks(self):
        cases = [
            case("A", "oxytocin", 0, "2026-08-01"),
            case("A", "misoprostol", 2, "2026-08-01"),
            case("B", "oxytocin", 4, "2026-08-01"),
        ]
        outcomes = {("A", "oxytocin"): 5, ("A", "misoprostol"): 0, ("B", "oxytocin"): 3}
        metrics = score_calls(cases, outcomes, capacity=1)
        self.assertEqual(metrics["facility_calls"], 1)
        self.assertEqual(metrics["product_checks"], 2)
        self.assertEqual(metrics["shortage_calls"], 1)
        self.assertEqual(metrics["shortage_product_checks"], 1)
        self.assertEqual(metrics["missed_shortage_products"], 1)
        self.assertEqual(metrics["random_candidate_expected_shortage_calls"], 1)

    def test_baselines_use_visible_stock_and_report_age(self):
        cases = [
            case("A", "oxytocin", 9, "2026-08-01"),
            case("B", "oxytocin", 0, "2026-09-01"),
            case("C", "oxytocin", "", ""),
        ]
        self.assertEqual(order_cases(cases, "SupplySignal gap"), cases)
        self.assertEqual(order_cases(cases, "Reported-zero first")[0]["facility_id"], "B")
        self.assertEqual(order_cases(cases, "Oldest-report first")[0]["facility_id"], "C")


if __name__ == "__main__":
    unittest.main()
