import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from beavers_choice.agents import assess_order, process_rule_order
from beavers_choice.database import (
    db_engine,
    generate_financial_report,
    get_stock_level,
    init_database,
    paper_supplies,
)
from beavers_choice.pricing import parse_requested_items


class BusinessFlowTests(unittest.TestCase):
    def setUp(self):
        init_database(db_engine, seed=137)

    def tearDown(self):
        db_engine.dispose()

    def test_first_sample_request_maps_to_seeded_catalog_stock(self):
        request = (
            "200 sheets of A4 glossy paper, 100 sheets of heavy cardstock (white), "
            "100 sheets of colored paper (assorted colors)."
        )
        assessment = assess_order(request, "2025-04-01")
        self.assertEqual(assessment["status"], "eligible")
        self.assertEqual(
            [(item["item_name"], item["quantity"]) for item in assessment["items"]],
            [("Glossy paper", 200), ("Cardstock", 100), ("Colored paper", 100)],
        )
        self.assertEqual(
            [item["available"] for item in assessment["items"]],
            [587, 595, 788],
        )

    def test_unknown_products_are_not_reported_as_stock_shortages(self):
        assessment = assess_order("500 sheets of A3 matte paper and 200 balloons.", "2025-04-01")
        self.assertEqual(assessment["status"], "rejected")
        self.assertEqual({reason["code"] for reason in assessment["reasons"]}, {"not_in_catalog"})
        self.assertTrue(all(item["item_name"] is None for item in assessment["items"]))
        self.assertTrue(all(item["shortage"] == 0 for item in assessment["items"]))

    def test_rejection_explains_each_catalog_and_non_catalog_line(self):
        outcome = process_rule_order(
            "500 sheets of colorful poster paper, 300 rolls of streamers, and 200 balloons for the parade. Deliver by April 15, 2025.",
            "2025-04-03",
            "mixed-rejection",
        )
        self.assertEqual(outcome["status"], "rejected")
        self.assertIn("balloons is not in our product catalog", outcome["response"])
        self.assertIn("500 requested", outcome["response"])
        self.assertIn("300 requested", outcome["response"])

    def test_full_dataset_meets_rubric_without_negative_inventory(self):
        requests = pd.read_csv(PROJECT_ROOT / "input_output" / "inputs" / "quote_requests_sample.csv")
        requests.loc[:, "request_date"] = pd.to_datetime(requests["request_date"], format="%m/%d/%y")
        requests = requests.sort_values("request_date", kind="stable")
        fulfilled = 0
        rejected = 0
        cash_changes = 0

        for original_index, row in requests.iterrows():
            request_date = row["request_date"].strftime("%Y-%m-%d")
            cash_before = generate_financial_report(request_date)["cash_balance"]
            outcome = process_rule_order(
                row["request"],
                request_date,
                f"unit-{original_index + 1:03d}",
            )
            cash_after = generate_financial_report(request_date)["cash_balance"]
            fulfilled += outcome["status"] == "accepted"
            rejected += outcome["status"] == "rejected"
            cash_changes += abs(cash_after - cash_before) > 0.005

        self.assertEqual(len(requests), 20)
        self.assertGreaterEqual(fulfilled, 3)
        self.assertGreaterEqual(cash_changes, 3)
        self.assertGreater(rejected, 0)
        final_date = requests["request_date"].max().strftime("%Y-%m-%d")
        stock_levels = [
            int(get_stock_level(item["item_name"], final_date)["current_stock"].iloc[0])
            for item in paper_supplies
        ]
        self.assertGreaterEqual(min(stock_levels), 0)


if __name__ == "__main__":
    unittest.main()