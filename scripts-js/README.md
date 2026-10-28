# JavaScript scripts

| Script | What it does |
|---|---|
| `build_cashflow_projection.mjs` | Builds the BNPL cash-flow workbook. Reads `data/soupop_cashflow_source.json` (from `python3 scripts-py/fetch_cashflow_data.py`) and writes `reports/Soupop BNPL Cash Flow Projection.xlsx` plus preview images in `data/cashflow-preview/`. |

Run from the workspace root with Node 18 or newer: `node scripts-js/build_cashflow_projection.mjs`. It needs the `@oai/artifact-tool` package, which is available inside the Codex environment it was written in, not from the public npm registry. Method: `business-logic/Analytics/cash-flow.md`.
