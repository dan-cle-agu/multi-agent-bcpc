# Beaver's Choice Paper Company Multi-Agent Project

Course entrypoint and supplied database helpers remain in `project_starter.py`. The multi-agent tools, three specialist workers, and orchestrator are implemented in `template.py` and called by the starter's `run_test_scenarios()`.

## Project files

- `project_starter.py`: product catalog, deterministic inventory seed, SQLite helpers, and CSV evaluator.
- `template.py`: smolagents inventory, pricing, sales, and managed orchestrator agents; it receives the starter helpers as dependencies.
- `quote_requests.csv`: historical customer inquiries loaded into the `quote_requests` table.
- `quotes.csv`: historical quote totals, explanations, and metadata loaded into the `quotes` table.
- `quote_requests_sample.csv`: 20 dated scenarios replayed by `run_test_scenarios()`.
- `test_results.csv`: required root-level evaluation output. A mirror is also written to `input_output/outputs/`.
- `tests/test_template_flow.py`: deterministic integration checks derived from the seed and supplied request CSVs.

The database and all CSV/output paths resolve relative to `project_starter.py`, even when launched from the parent workspace directory.

## Setup and run

```powershell
python -m pip install -r requirements.txt
# From the project root
python .\project_starter.py
```

From the parent `samples` directory, run `python .\multi-agent-bcpc\project_starter.py`.

Configure `.env` with `UDACITY_OPENAI_API_KEY` for live model delegation. To replay the evaluator without API calls, set `$env:BCPC_USE_LLM="0"` before running it; deterministic business rules still exercise the full catalog, inventory, quote, and ledger path.

```powershell
$env:BCPC_USE_LLM = "0"
python .\project_starter.py
```

Run regression tests without API calls:

```powershell
python -m unittest discover -s tests -v
```

## Design and results

- Agent/tool mapping: [input_output/outputs/workflow_diagram.md](input_output/outputs/workflow_diagram.md)
- Architecture: [docs/architecture.md](docs/architecture.md)
- Evaluation summary: [docs/evaluation_summary.md](docs/evaluation_summary.md)
- Reflection: [docs/reflection_report.md](docs/reflection_report.md)
