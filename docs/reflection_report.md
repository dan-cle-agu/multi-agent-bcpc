# Reflection report

## Architecture and design
The implementation uses smolagents with one orchestrator and three managed workers. The orchestrator has no direct business tools: it delegates the inventory assessment first, then pricing for eligible requests, and sales finalization only after a valid quote. Each tool's ownership and the JSON passed between stages are shown in the workflow diagram.

The LLM coordinates the tasks, while deterministic application logic remains authoritative for catalog aliases, stock and due-date checks, discount calculations, and transaction writes. This prevents fluent model responses from overriding unsupported products, incorrect stock figures, or invalid quote totals. Sales commits are atomic and keyed by request, so retries do not double-charge or duplicate units.

## Evaluation method
The evaluator resets the database to the fixed seed, processes every row in the supplied 20-request sample in stable date order, and records a row-level disposition. Each output row includes the normalized request items, the before/after cash and inventory values, ledger totals, reconciliation status, orchestration mode, delegated worker names, and the customer-facing explanation.

Accepted orders write item sales and any required supplier purchase/receipt entries to the ledger. Orders with unsupported catalog products or deadlines that cannot be met are rejected with those reasons. The runner fails if the dataset is incomplete, the rubric minimums are missed, fewer than three fulfilled orders complete the managed-agent sequence, or any result fails ledger reconciliation.

The saved [evaluation output](../input_output/outputs/test_results.csv) is the source of truth for the final counts and financial values; its entries are computed from the transaction ledger rather than hard-coded in this report.

## Strengths
- Distinct agent roles and real managed-agent calls in the prescribed sequence.
- Catalog validation distinguishes unsupported products from temporarily unavailable stock.
- Projected stock accounts for previously committed future receipts and sales, preventing over-selling.
- Customer explanations use catalog facts and avoid exposing internal financial details.
- A deterministic fallback allows the same business checks and output gates to run without an API key.

## Future improvements
1. Expand catalog alias coverage using additional labeled request examples and parser regression tests.
2. Add a separate forecasting worker only when historical demand data can validate its recommendations.
3. Add structured audit views for request-level supplier and inventory commitments.
