import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import project_starter as starter
from template import create_multi_agent_system, parse_requested_items


def starter_helpers():
    return {
        "db_engine": starter.db_engine,
        "paper_supplies": starter.paper_supplies,
        "create_transaction": starter.create_transaction,
        "get_all_inventory": starter.get_all_inventory,
        "get_stock_level": starter.get_stock_level,
        "get_supplier_delivery_date": starter.get_supplier_delivery_date,
        "get_cash_balance": starter.get_cash_balance,
        "generate_financial_report": starter.generate_financial_report,
        "search_quote_history": starter.search_quote_history,
    }


class TemplateFlowTests(unittest.TestCase):
    def setUp(self):
        starter.init_database(starter.db_engine, seed=137)
        self.system = create_multi_agent_system(starter_helpers(), use_llm=False)

    def tearDown(self):
        starter.db_engine.dispose()

    def test_seeded_inventory_is_reproducible(self):
        first = starter.generate_sample_inventory(starter.paper_supplies, seed=137)
        second = starter.generate_sample_inventory(starter.paper_supplies, seed=137)
        pd.testing.assert_frame_equal(first, second)
        generated_stock = first.set_index("item_name")["current_stock"].to_dict()
        ledger_stock = {
            name: int(starter.get_stock_level(name, "2025-04-01")["current_stock"].iloc[0])
            for name in generated_stock
        }
        self.assertEqual(ledger_stock, generated_stock)

    def test_unsupported_items_are_not_stock_shortages(self):
        requests = pd.read_csv(PROJECT_DIR / "quote_requests_sample.csv")
        selected = None
        for request_id, row in requests.iterrows():
            items = parse_requested_items(row["request"], starter.paper_supplies)
            unknown = [item for item in items if item["catalog_status"] == "not_in_catalog"]
            if unknown:
                selected = (request_id, row, unknown)
                break
        self.assertIsNotNone(selected, "The provided request sample must include an unsupported catalog item.")
        request_id, row, unknown = selected
        request_date = datetime.strptime(str(row["request_date"]), "%m/%d/%y").strftime("%Y-%m-%d")
        outcome = self.system.handle_request(row["request"], request_date, f"sample-unknown-{request_id}")
        self.assertEqual(outcome["status"], "rejected")
        self.assertEqual(outcome["reason"], "not_in_catalog")
        self.assertTrue(all(item["item_name"] is None for item in unknown))
        for item in unknown:
            self.assertIn(f"{item['requested_name']} is not in our product catalog", outcome["response"])

    def test_runner_date_suffix_does_not_create_a_phantom_item(self):
        row = pd.read_csv(PROJECT_DIR / "quote_requests_sample.csv").iloc[0]
        request_date = datetime.strptime(str(row["request_date"]), "%m/%d/%y").strftime("%Y-%m-%d")
        original_items = parse_requested_items(row["request"], starter.paper_supplies)
        request = f"{row['request']} (Date of request: {request_date})"
        suffixed_items = parse_requested_items(request, starter.paper_supplies)
        self.assertEqual(suffixed_items, original_items)
        outcome = self.system.handle_request(request, request_date, "sample-date-suffix")
        self.assertEqual(outcome["status"], "accepted")
        self.assertEqual(len(outcome["assessment"]["items"]), 3)
        self.assertEqual(outcome["reason"], None)

    def test_all_sample_requests_meet_evaluation_minimums(self):
        source_requests = pd.read_csv(PROJECT_DIR / "quote_requests_sample.csv")
        requests = []
        for request_id, row in enumerate(source_requests.to_dict(orient="records"), start=1):
            try:
                request_date = datetime.strptime(str(row["request_date"]), "%m/%d/%y")
            except (TypeError, ValueError):
                continue
            requests.append((request_id, row, request_date))
        requests.sort(key=lambda entry: entry[2])
        accepted = 0
        rejected = 0
        cash_changes = 0

        for request_id, row, parsed_date in requests:
            request_date = parsed_date.strftime("%Y-%m-%d")
            before = starter.get_cash_balance(request_date)
            outcome = self.system.handle_request(
                row["request"], request_date, f"sample-{request_id:03d}"
            )
            after = starter.get_cash_balance(request_date)
            accepted += outcome["status"] == "accepted"
            rejected += outcome["status"] == "rejected"
            cash_changes += abs(after - before) > 0.005

        self.assertEqual(len(requests), 20)
        self.assertGreaterEqual(accepted, 3)
        self.assertGreaterEqual(rejected, 1)
        self.assertGreaterEqual(cash_changes, 3)
        final_date = requests[-1][2].strftime("%Y-%m-%d")
        stock_levels = [
            int(starter.get_stock_level(item["item_name"], final_date)["current_stock"].iloc[0])
            for item in starter.paper_supplies
        ]
        self.assertGreaterEqual(min(stock_levels), 0)

    def test_all_starter_helpers_are_registered_in_agent_tools(self):
        expected = {
            "inventory_assessment",
            "inventory_snapshot",
            "supplier_delivery",
            "quote_history",
            "quote_order",
            "sales_finalize",
            "cash_balance",
            "financial_report",
        }
        self.assertEqual(set(self.system.tools), expected)


if __name__ == "__main__":
    unittest.main()