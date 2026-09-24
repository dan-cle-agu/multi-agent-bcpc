# Reflection report

## Architecture and design
The solution uses a four-agent structure: one orchestrator and three worker agents. The orchestrator receives customer text, identifies the request type, and decides when to delegate to inventory, pricing, and sales functions. This keeps responsibilities separated, reducing overlap and preserving clear data flow.

The inventory agent validates stock availability against the request quantity and checks whether restocking by supplier can meet the customer deadline. The pricing agent consults historical quote patterns and computes a quote using a tiered discount model. The sales agent performs the final sale or rejects the request with explanation when the order is impossible.

This design follows the project constraints because the system stays within the five-agent limit and uses a clear operational flow: customer request -> inventory validation -> financial and quoting checks -> transaction logging -> customer-facing explanation.

## Evaluation results
The script was executed against the provided sample dataset and produced a `test_results.csv` file. The results demonstrate that the system accepted orders when stock and supplier lead times allowed it, while rejecting impossible orders with explicit rationale.

The accepted cases include multiple real sales transactions, which changed the cash balance on several requests. The rejected cases are also meaningful: impossible quantities, insufficient stock, or delivery windows that could not be met were clearly explained to the customer. This matches the rubric requirement of having both successful and unsuccessful outcomes.

## Strengths
- Clear separation of roles between inventory, pricing, and sales.
- Use of real helper functions from the starter project to keep the system grounded in the business data model.
- Explainable customer responses with reasons for acceptance, rejection, or restock planning.
- Deterministic execution that works without a live LLM key when the environment is not configured.

## Proposed improvements
1. Add a more advanced NLP parser to recognize more product variants and ambiguous wording in customer requests.
2. Expand the agent system with a dedicated forecasting agent to predict reorder timing and optimize inventory thresholds.
3. Add an audit module that stores customer-facing decisions and tracks acceptance/rejection reasons for easier reporting and operational monitoring.
