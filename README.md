# Beaver's Choice Paper Company Multi-Agent Project

An inventory, pricing, and sales workflow implemented with `smolagents`: one orchestrator delegates to three specialist agents, while deterministic business rules validate catalog matches, stock, delivery feasibility, quote totals, and ledger writes.

## Project layout

- `src/beavers_choice/`: application package (agents, pricing, database, and evaluation workflow).
- `input_output/inputs/`: source catalog history and sample request datasets.
- `input_output/outputs/`: generated evaluation CSV and workflow diagram.
- `docs/`: architecture, evaluation, and reflection documentation.
- `tests/`: API-free parser, ledger, and full-dataset regression checks.
- `project_starter.py`: compatible project entry point.

The six original starter files remain in the repository root for course compatibility; the application reads its organized input copies from `input_output/inputs/`.

## Setup and run

```bash
python -m pip install -r requirements.txt
python project_starter.py
```

Run the deterministic regression suite without making API calls:

```bash
python -m unittest discover -s tests -v
```

To use the live OpenAI-compatible endpoint, copy `.env.example` to `.env` and set `UDACITY_OPENAI_API_KEY`. Without a configured key, deterministic fallback still exercises catalog, stock, quote, and ledger rules; the full course evaluator intentionally fails its live managed-agent gate unless at least three fulfilled orders pass through the three workers. The generated report records the mode and successful worker tool calls.

## Results and design

- Evaluation: [input_output/outputs/test_results.csv](input_output/outputs/test_results.csv)
- Implemented agent/tool mapping: [input_output/outputs/workflow_diagram.md](input_output/outputs/workflow_diagram.md)
- Architecture: [docs/architecture.md](docs/architecture.md)
- Reflection and evaluation notes: [docs/reflection_report.md](docs/reflection_report.md), [docs/evaluation_summary.md](docs/evaluation_summary.md)
