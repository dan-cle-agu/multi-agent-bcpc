# Architecture overview

The solution follows a small multi-agent architecture with one orchestrator and three operational specialists.

## 1. Orchestrator agent
The orchestrator receives customer requests and routes them to the appropriate business functions.

## 2. Inventory agent
This agent validates stock availability, compares requested quantities against current levels, and checks delivery feasibility.

## 3. Pricing agent
This component estimates price totals using the catalog data and the discount policy while consulting historical quote records when needed.

## 4. Sales agent
The sales agent finalizes accepted orders and records the resulting transactions in the SQLite ledger.

## Flow
Customer request -> orchestrator -> inventory check -> pricing check -> sales finalization -> customer response
