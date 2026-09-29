import json
from datetime import datetime

import pandas as pd
from sqlalchemy import text

from .agents import run_multi_agent_system
from .database import OUTPUT_DIR, INPUT_DIR, db_engine, generate_financial_report, init_database


def _request_ledger_summary(request_key: str) -> dict:
    query = text(
        "SELECT COUNT(*) AS transaction_count, "
        "SUM(CASE WHEN transaction_type = 'sales' THEN price ELSE 0 END) AS sales_total, "
        "SUM(CASE WHEN transaction_type = 'stock_orders' THEN price ELSE 0 END) AS purchase_total "
        "FROM transactions WHERE request_key = :request_key"
    )
    with db_engine.connect() as connection:
        result = connection.execute(query, {"request_key": request_key}).mappings().one()
    return {
        "transaction_count": int(result["transaction_count"] or 0),
        "sales_total": round(float(result["sales_total"] or 0), 2),
        "purchase_total": round(float(result["purchase_total"] or 0), 2),
    }


def run_test_scenarios():
    print("Initializing Database...")
    init_database(db_engine, seed=137)
    try:
        quote_requests_sample = pd.read_csv(INPUT_DIR / "quote_requests_sample.csv")
        quote_requests_sample.insert(0, "request_id", range(1, len(quote_requests_sample) + 1))
        quote_requests_sample.loc[:, "request_date"] = pd.to_datetime(
            quote_requests_sample["request_date"], format="%m/%d/%y", errors="coerce"
        )
        quote_requests_sample = quote_requests_sample.dropna(subset=["request_date"]).sort_values(
            "request_date", kind="stable"
        )
    except Exception as exc:  # pragma: no cover - diagnostic path
        print(f"FATAL: Error loading test data: {exc}")
        return

    results = []
    for idx, row in quote_requests_sample.iterrows():
        request_date = row["request_date"].strftime("%Y-%m-%d")
        request_id = int(row["request_id"])
        request_key = f"sample-{request_id:03d}"
        before = generate_financial_report(request_date)
        print(f"\n=== Request {idx + 1} ===")
        print(f"Context: {row['job']} organizing {row['event']}")
        print(f"Request Date: {request_date}")
        print(f"Cash Balance: ${before['cash_balance']:.2f}")
        print(f"Inventory Value: ${before['inventory_value']:.2f}")

        outcome = run_multi_agent_system(str(row["request"]), request_date, request_key)
        after = generate_financial_report(request_date)
        ledger = _request_ledger_summary(request_key)
        quote_total = round(float(outcome["quote"].get("total", 0)), 2)
        if outcome["status"] == "accepted":
            ledger_reconciled = abs(ledger["sales_total"] - quote_total) <= 0.01
        else:
            ledger_reconciled = ledger["transaction_count"] == 0 and ledger["sales_total"] == 0

        print(f"Disposition: {outcome['status']}")
        print(
            f"Orchestration: {outcome['orchestration_mode']}; delegated="
            f"{','.join(outcome['delegated_agents']) or 'none'}; complete={outcome['delegation_complete']}"
        )
        if outcome["manager_error_type"]:
            print(f"Manager error type: {outcome['manager_error_type']}")
        print(f"Response: {outcome['response']}")
        print(f"Cash after request: ${after['cash_balance']:.2f}")
        print(f"Ledger reconciled: {ledger_reconciled}")

        response_items = outcome["assessment"].get("items", [])
        results.append(
            {
                "request_id": request_id,
                "request_key": request_key,
                "request_date": request_date,
                "status": "fulfilled" if outcome["status"] == "accepted" else "rejected",
                "reason": outcome.get("reason") or "",
                "requested_items": json.dumps(response_items, ensure_ascii=False),
                "delivery_date": outcome["assessment"].get("delivery_date", ""),
                "quote_total": quote_total if outcome["status"] == "accepted" else "",
                "cash_balance_before": round(float(before["cash_balance"]), 2),
                "cash_balance_after": round(float(after["cash_balance"]), 2),
                "cash_changed": abs(float(after["cash_balance"]) - float(before["cash_balance"])) > 0.005,
                "inventory_value_before": round(float(before["inventory_value"]), 2),
                "inventory_value_after": round(float(after["inventory_value"]), 2),
                "cash_balance": round(float(after["cash_balance"]), 2),
                "inventory_value": round(float(after["inventory_value"]), 2),
                "transaction_count": ledger["transaction_count"],
                "ledger_sales_total": ledger["sales_total"],
                "ledger_purchase_total": ledger["purchase_total"],
                "ledger_reconciled": ledger_reconciled,
                "orchestration_mode": outcome["orchestration_mode"],
                "delegated_agents": ";".join(outcome["delegated_agents"]),
                "worker_tool_calls": json.dumps(outcome["worker_tool_calls"], ensure_ascii=False),
                "delegation_complete": outcome["delegation_complete"],
                "manager_error_type": outcome["manager_error_type"] or "",
                "response": outcome["response"],
            }
        )

    final_date = quote_requests_sample["request_date"].max().strftime("%Y-%m-%d")
    final_report = generate_financial_report(final_date)
    results_df = pd.DataFrame(results)
    output_path = OUTPUT_DIR / "test_results.csv"
    results_df.to_csv(output_path, index=False)
    fulfilled_count = int((results_df["status"] == "fulfilled").sum())
    rejected_count = int((results_df["status"] == "rejected").sum())
    cash_change_count = int(results_df["cash_changed"].sum())
    reconciled_count = int(results_df["ledger_reconciled"].sum())
    delegated_fulfillment_count = int(
        ((results_df["status"] == "fulfilled") & results_df["delegation_complete"]).sum()
    )
    print("\n===== FINAL FINANCIAL REPORT =====")
    print(f"Final Cash: ${final_report['cash_balance']:.2f}")
    print(f"Final Inventory: ${final_report['inventory_value']:.2f}")
    print(
        f"Evaluation: {len(results_df)} requests, {fulfilled_count} fulfilled, {rejected_count} rejected, "
        f"{cash_change_count} cash-changing requests, {reconciled_count} ledger-reconciled"
    )
    print(f"Delegated fulfilled requests: {delegated_fulfillment_count}")

    if len(results_df) != len(quote_requests_sample) or fulfilled_count < 3 or cash_change_count < 3 or rejected_count == 0:
        raise RuntimeError("Evaluation did not meet the minimum request, fulfillment, cash-change, and rejection criteria.")
    if reconciled_count != len(results_df):
        raise RuntimeError("At least one request result does not reconcile against the transaction ledger.")
    if delegated_fulfillment_count < 3:
        raise RuntimeError("Fewer than three fulfilled requests completed the inventory, pricing, and sales delegation sequence.")

    return results
