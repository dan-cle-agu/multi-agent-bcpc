import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from .agents import run_multi_agent_system
from .database import OUTPUT_DIR, INPUT_DIR, db_engine, generate_financial_report, init_database


def run_test_scenarios():
    print("Initializing Database...")
    init_database(db_engine, seed=137)
    try:
        quote_requests_sample = pd.read_csv(INPUT_DIR / "quote_requests_sample.csv")
        quote_requests_sample = quote_requests_sample.assign(
            request_date=pd.to_datetime(
                quote_requests_sample["request_date"], format="%m/%d/%y", errors="coerce"
            )
        )
        quote_requests_sample = quote_requests_sample.dropna(subset=["request_date"]).sort_values("request_date")
    except Exception as exc:  # pragma: no cover - diagnostic path
        print(f"FATAL: Error loading test data: {exc}")
        return

    initial_date = quote_requests_sample["request_date"].min().strftime("%Y-%m-%d")
    report = generate_financial_report(initial_date)
    current_cash = report["cash_balance"]
    current_inventory = report["inventory_value"]

    results = []
    for idx, row in quote_requests_sample.iterrows():
        request_date = row["request_date"].strftime("%Y-%m-%d")
        print(f"\n=== Request {idx + 1} ===")
        print(f"Context: {row['job']} organizing {row['event']}")
        print(f"Request Date: {request_date}")
        print(f"Cash Balance: ${current_cash:.2f}")
        print(f"Inventory Value: ${current_inventory:.2f}")

        request_with_date = f"{row['request']} (Date of request: {request_date})"
        response = run_multi_agent_system(request_with_date, request_date)

        report = generate_financial_report(request_date)
        current_cash = report["cash_balance"]
        current_inventory = report["inventory_value"]

        print(f"Response: {response}")
        print(f"Updated Cash: ${current_cash:.2f}")
        print(f"Updated Inventory: ${current_inventory:.2f}")

        results.append(
            {
                "request_id": idx + 1,
                "request_date": request_date,
                "cash_balance": current_cash,
                "inventory_value": current_inventory,
                "response": response,
            }
        )
        time.sleep(0.2)

    final_date = quote_requests_sample["request_date"].max().strftime("%Y-%m-%d")
    final_report = generate_financial_report(final_date)
    print("\n===== FINAL FINANCIAL REPORT =====")
    print(f"Final Cash: ${final_report['cash_balance']:.2f}")
    print(f"Final Inventory: ${final_report['inventory_value']:.2f}")

    output_path = OUTPUT_DIR / "test_results.csv"
    pd.DataFrame(results).to_csv(output_path, index=False)
    return results
