# Architecture overview

`project_starter.py` owns the course-provided catalog, SQLite helpers, deterministic seed, and scenario runner. It passes those helpers into `template.py`; that file defines all agent tools and agent orchestration. The tool/data flow is shown in [the workflow diagram](../input_output/outputs/workflow_diagram.md).

## Orchestrator
`orchestrator_agent` is a `smolagents.ToolCallingAgent` with no direct business tools and three managed workers. It delegates inventory first, pricing only for eligible requests, and sales only for priced requests.

## Inventory worker
`inventory_agent` maps request aliases to starter catalog names, distinguishes unsupported goods from out-of-stock goods, reads current stock with `get_stock_level`, projects existing dated transactions, and evaluates the requested deadline using `get_supplier_delivery_date`. `inventory_snapshot_tool` exposes `get_all_inventory`.

## Pricing worker
`pricing_agent` uses `search_quote_history` through `quote_history_tool` and prices canonical lines with catalog prices and quantity discounts through `quote_order_tool`.

## Sales worker
`sales_agent` validates the structured assessment and quote before finalizing. It records purchases, receipts, and sales through the starter's `create_transaction` helper and can report `get_cash_balance` and `generate_financial_report` results. A SQLite order key prevents duplicate finalization within a run.

## Execution and state
# Architecture overview

The course entrypoint stays in `project_starter.py`: it owns the catalog, SQLite engine, supplied database helpers, CSV evaluation loop, and root-level `test_results.csv`. It constructs and calls the system implemented in `template.py`, keeping agent code out of the starter helper section while preserving the instructor's expected runner. The actual agent/tool flow is in [workflow_diagram.md](../input_output/outputs/workflow_diagram.md).

## Agents

- `orchestrator_agent`: a smolagents `ToolCallingAgent` with the three specialist agents as `managed_agents`; delegates inventory, pricing, and sales in order.
- `inventory_agent`: maps natural-language lines to catalog items; invokes stock, inventory snapshot, and supplier ETA tools.
- `pricing_agent`: queries historical quotes and calculates itemized prices/discounts from the normalized assessment.
- `sales_agent`: calls the guarded finalizer only for eligible, quoted orders and can call cash and financial-report tools.

## Source of truth

The functions in `project_starter.py` remain the data API injected into the tools: `create_transaction`, `get_all_inventory`, `get_stock_level`, `get_supplier_delivery_date`, `get_cash_balance`, `generate_financial_report`, and `search_quote_history`. The deterministic parser validates catalog membership; stock and due dates are checked against the transaction ledger; sales writes use `create_transaction`. The LLM coordinates work but cannot turn an unsupported product or impossible delivery date into an accepted sale.

## State and tests

`generate_sample_inventory(..., seed=137)` makes the initial selected items and quantities reproducible. The runner loads the provided 20-row sample in stable date order and stores dispositions, reasons, cash changes, inventory values, delegation mode, and ledger reconciliation in `test_results.csv`. The no-API regression suite derives stock expectations from the generator and validates catalog errors and transactions using actual rows from the supplied sample.
