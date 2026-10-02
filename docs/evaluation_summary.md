# Evaluation summary

The evaluator in `project_starter.py` runs the complete root-level `quote_requests_sample.csv` after resetting the SQLite ledger to seed `137`. It writes the course artifact to root-level `test_results.csv` and mirrors it to `input_output/outputs/test_results.csv` when that folder exists.

## Evidence captured
- Request disposition and rejection reason.
- Normalized item names, quantities, catalog status, current/projected availability, shortage, and delivery date.
- Quote total, cash and inventory before/after, and request-specific transaction totals.
- `ledger_reconciled`, `orchestration_mode`, and `delegated_agents` for each request.

## Quality gates
- All 20 source requests are represented.
- At least three requests are fulfilled and at least three change the cash balance.
- Both fulfilled and rejected outcomes are present.
- Every row reconciles to the ledger; fulfilled orders record sales equal to the quote total.
- Live delegation must be verified separately with a valid, non-expired API credential; deterministic tests do not prove live model activity.
- Stock is validated against catalog entries and committed future transactions, and cannot be sold below zero.

See root-level `test_results.csv` for the latest run's counts and responses. The evaluator raises an error if the sample is incomplete, fewer than three orders are fulfilled, no requests are rejected, or fewer than three requests change cash.

## Latest evaluation

The live run on `develop/starter-template` completed under the user's `.venv` with the renewed API key. It processed all 20 requests and produced 5 fulfilled, 15 rejected, 5 cash-changing requests, and 20/20 ledger-reconciled rows. Every row used `smolagents_managed_agents`; all 5 fulfilled requests delegated through inventory, pricing, and sales, with no manager errors. Final cash was `$45,310.90`; final inventory value was `$4,660.05`.

The previous credential had expired on 2026-09-29. The Python 3.14/Pandas 2.2.3 segmentation fault was traced to `pandas.to_datetime` in the runner/test; replacing it with `datetime.strptime` and stable Python sorting eliminated the crash in the virtual environment. The renewed live run then completed with exit code 0.
