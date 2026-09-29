# Architecture overview

The project uses `smolagents` with four distinct agents: a manager/orchestrator and three specialist workers. The exact tool ownership and information flow are mapped in [the workflow diagram](../input_output/outputs/workflow_diagram.md).

## Orchestrator
`orchestrator_agent` is a `ToolCallingAgent` with an empty direct-tool list and the inventory, pricing, and sales workers registered as `managed_agents`. It invokes inventory first, pricing only for an eligible assessment, and sales only for a valid quote.

## Inventory worker
`inventory_agent` resolves customer item descriptions to canonical catalog entries, distinguishes unsupported items from stock shortages, checks the transaction ledger, projects already committed receipts and sales through the deadline, and estimates supplier delivery dates.

## Pricing worker
`pricing_agent` prices the complete inventory assessment with catalog unit prices and the tiered quantity discounts. It receives normalized item names and quantities from inventory instead of independently interpreting free-form aliases.

## Sales worker
`sales_agent` finalizes an eligible quoted order in one transaction. It writes purchase costs, future receipts, sales entries, and a unique request record; repeated finalization for the same request is idempotent.

## Source of truth and fallback
The LLM coordinates specialist work and may summarize decisions, but deterministic application code owns item mapping, stock/deadline validation, quote totals, and database writes. When no model is configured or a live call fails, the same validated business flow runs locally; the evaluation output records whether managed delegation completed.
