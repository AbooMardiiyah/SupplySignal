import unittest
from datetime import date

from supplysignal.worksheet import call_worksheet


class CallWorksheetTest(unittest.TestCase):
    def test_capacity_keeps_all_products_for_selected_facility_and_marks_unknowns(self):
        def case(facility, product):
            return dict(facility_id=facility, facility_name=f"PHC {facility}",
                        commodity_id=product, commodity_name=product, signal="Missing report",
                        action="verify_stock", next_step="Confirm a count", last_report_period="2026-08")
        text = call_worksheet([case("A", "Drug1"), case("B", "Drug2"), case("A", "Drug3")],
                              date(2026, 10, 4), capacity=1)
        self.assertIn("Drug1", text)
        self.assertIn("Drug3", text)
        self.assertNotIn("Drug2", text)
        self.assertIn("UNKNOWN, never zero", text)
        self.assertIn("2026-10-04", text)
        self.assertIn("simulated inventory", text)
        self.assertIn("no automatic upload", text)

    def test_empty_sheet_does_not_claim_all_facilities_are_safe(self):
        text = call_worksheet([], date(2026, 10, 4))
        self.assertIn("not proof of universal availability", text)


if __name__ == "__main__":
    unittest.main()
