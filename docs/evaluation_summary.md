# Evaluation summary

The evaluator runs the complete `quote_requests_sample.csv` dataset after resetting the SQLite ledger to its deterministic seed. The saved CSV is generated from per-request execution and ledger queries.

## Evidence captured
- Request disposition and rejection reason.
- Normalized item names, quantities, catalog status, current/projected availability, shortage, and delivery date.
- Quote total, cash and inventory before/after, and request-specific transaction totals.
- `ledger_reconciled`, `orchestration_mode`, `delegated_agents`, successful worker tool calls, and `delegation_complete`.

## Quality gates
- All 20 source requests are represented.
- At least three requests are fulfilled and at least three change the cash balance.
- Both fulfilled and rejected outcomes are present.
- Every row reconciles to the ledger; fulfilled orders record sales equal to the quote total.
- At least three fulfilled orders complete the inventory -> pricing -> sales managed-agent sequence.
- Stock is validated against catalog entries and committed future transactions, and cannot be sold below zero.

See [test_results.csv](../input_output/outputs/test_results.csv) for the measured final counts and customer-facing responses. The evaluator raises an error if any gate is not met.

## Live evaluation result

The complete 20-row run used the configured OpenAI-compatible model and reported 3 managed workers. It produced 5 fulfilled and 15 rejected requests, with 5 cash-changing requests and all 20 rows reconciled to the ledger. Tool-call evidence records 20 successful inventory assessments, 5 whole-order pricing calls, and 5 sales finalizations. All 5 fulfilled orders completed the inventory, pricing, and sales sequence. No negative available-stock values were recorded.

- Final cash balance: `$45,310.90`
- Final inventory value: `$4,660.05`
