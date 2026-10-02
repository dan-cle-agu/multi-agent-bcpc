# Reflection report

## Architecture and workflow
`project_starter.py` retains the course catalog, SQLite helpers, deterministic seed, and `run_test_scenarios()` evaluator. It passes those helpers to `template.py`, which implements four roles with smolagents: an orchestrator plus inventory, pricing, and sales workers. Inventory runs first; pricing runs only for eligible requests; sales finalization runs only after a valid quote.

Deterministic code resolves catalog aliases, checks stock and deadlines, calculates discounts, and guards sales. The model coordinates workers when a valid API credential is available; it does not determine catalog membership or invent stock values. The system records a unique request key to avoid duplicate finalization within an evaluation run.

## Evaluation method and results
The runner resets SQLite with seed `137`, processes all 20 rows in stable date order, and writes root-level `test_results.csv` plus a mirror under `input_output/outputs/`. Rows record status, reason, quote, cash/inventory state, orchestration mode, and ledger reconciliation.

The live run on 2026-10-02 used the renewed API credential in the user's `.venv`. It recorded **5 fulfilled**, **15 rejected**, **5 cash-changing** requests, and **20/20 reconciled** rows. Every request used the managed-agent route; all five fulfilled requests delegated to inventory, pricing, and sales, with no manager errors. Final cash was `$45,310.90` and inventory value was `$4,660.05`. The row-level [root test_results.csv](../test_results.csv) is the detailed result.

## Strengths
- The entrypoint exposes the supplied helpers and course evaluator; agent tools are defined in the requested `template.py`.
- Catalog validation distinguishes unsupported products from temporarily unavailable stock.
- Projected stock accounts for previously committed future receipts and sales, preventing over-selling.
- Customer explanations use catalog facts and avoid exposing internal financial details.
- Seeded inventory and deterministic tests make stock movement reproducible.
- The five-test suite derives expected stock from the fixed seed and selects valid/invalid customer lines from the supplied CSV rather than using a hand-authored inventory story.

One remaining limit is that purchase, receipt, and sale writes use multiple calls to `create_transaction`; a database failure between calls could leave a partial order.

## Future improvements
1. Add CI that runs deterministic tests on supported Python/Pandas combinations and a credential-gated live smoke test.
2. Make purchase, receipt, and sale writes atomic in a single database transaction.
3. Extend parser regression cases using additional real request variants.
