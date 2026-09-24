# Beaver's Choice Paper Company Multi-Agent Project

This project implements a compact multi-agent workflow for inventory review, quote generation, and sales finalization.

## Repository structure

```text
multi-agent-bcpc/
├── docs/
│   ├── README.md
│   ├── architecture.md
│   └── evaluation_summary.md
├── input_output/
│   ├── README.md
│   ├── inputs/
│   │   ├── quote_requests.csv
│   │   ├── quote_requests_sample.csv
│   │   └── quotes.csv
│   └── outputs/
│       └── test_results.csv
├── src/
│   └── beavers_choice/
│       ├── __init__.py
│       ├── agents.py
│       ├── database.py
│       ├── main.py
│       ├── pricing.py
│       └── workflow.py
├── .env.example
├── .env
├── project_starter.py
├── requirements.txt
├── workflow_diagram.md
├── reflection_report.md
└── munder_difflin.db
```

## How to run

```bash
python project_starter.py
```

This wrapper loads the modular package from `src/` and executes the multi-agent workflow.
