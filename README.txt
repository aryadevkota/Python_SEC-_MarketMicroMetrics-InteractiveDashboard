# Market Microstructure AI Dashboard

A financial data pipeline and interactive analytics dashboard for exploring
SEC market microstructure metrics across equities and ETPs. Built with
Python, SQLite, Streamlit, and the HuggingFace Inference API.

---

## Overview

This project ingests, transforms, and visualizes quantile-bucketed market
microstructure data including odd-lot rates, hidden order rates,
cancel-to-trade ratios, and trade volume sourced from SEC equity market
structure datasets. An embedded conversational assistant allows analysts
to query the data in plain English without writing SQL.

The ETL pipeline, data contracts, configuration, and dashboard are fully
decoupled, making it straightforward to swap data sources, databases, or
LLM providers independently.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Data Layer                           │
│  Raw CSV (SEC)  ->  etl.py  ->  SQLite (market_metrics) │
│                  (PyArrow + Pandas + Pydantic)          │
└─────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────────┐
│                 Presentation Layer                      │
│         app.py  (Streamlit Dashboard)                   │
│   ┌──────────────────┐   ┌──────────────────────────┐  │
│   │  Plotly Charts   │   │  AI Chat Assistant       │  │
│   │  (Interactive)   │   │  (HuggingFace Inference) │  │
│   └──────────────────┘   └──────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## Features

- **PyArrow ingestion** -- C++ CSV reader for fast file parsing, with Pandas
  for transformation and NumPy for vectorized feature engineering
- **Pydantic v2 schema enforcement** -- every record is validated against a
  typed data contract before database insertion
- **Log-transformed features** -- `log1p(metric_value)` is added automatically
  to handle right-skewed distributions common in financial microstructure data
- **Dual index strategy** -- SQLite indexes on `(metric_name, asset_class)`
  and `(sort_variable, quantile_bucket)` for fast query performance on large datasets
- **Conversational assistant** -- question routing dispatches queries to the
  appropriate SQL aggregation, then enriches results with a Mistral-7B
  narrative via the HuggingFace Inference API
- **Graceful degradation** -- if the API is unavailable, formatted SQL results
  are returned directly; the dashboard never surfaces raw error tracebacks
- **Environment-based configuration** -- all paths and credentials are resolved
  from environment variables via `config.py`; no hardcoded paths in the codebase

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Data ingestion | PyArrow | Fast CSV parsing |
| Transformation | Pandas, NumPy | Data reshaping and feature engineering |
| Validation | Pydantic v2 | Schema enforcement and data contracts |
| Storage | SQLite | Embedded relational database |
| Dashboard | Streamlit | Interactive web UI |
| Visualization | Plotly | Interactive charting |
| LLM | HuggingFace Inference API | Natural language data querying |
| Configuration | python-dotenv | Environment-based config management |
| ML | scikit-learn | Random Forest regression |

---

## Project Structure

```
PythonProj_MarketVolatility/
├── .env                  # API credentials and path overrides (never committed)
├── .gitignore
├── requirements.txt      # Pinned dependencies
├── config.py             # Central configuration -- all env vars resolved here
├── schemas.py            # Pydantic v2 data contracts
├── etl.py                # ETL pipeline -- Extract, Transform, Validate, Load
├── app.py                # Streamlit dashboard and AI chat assistant
└── run_dashboard.py      # Pre-flight checks and Streamlit launch script
```

---

## Data Model

All CSV files are normalized into a single `market_metrics` table:

```sql
CREATE TABLE market_metrics (
    trade_date       TEXT     NOT NULL,  -- YYYYMMDD
    asset_class      TEXT     NOT NULL,  -- 'stock' | 'etp'
    metric_name      TEXT     NOT NULL,  -- 'oddlot_rate' | 'hidden_rate' | ...
    sort_variable    TEXT     NOT NULL,  -- 'Market Cap' | 'Volatility' | ...
    quantile_type    TEXT     NOT NULL,  -- 'decile' | 'quartile'
    quantile_bucket  INTEGER  NOT NULL,  -- 1 (lowest) to 10 (highest)
    metric_value     REAL     NOT NULL,  -- raw metric
    log_metric_value REAL     NOT NULL   -- log1p(metric_value)
);

CREATE INDEX idx_metric_asset  ON market_metrics (metric_name, asset_class);
CREATE INDEX idx_sort_bucket   ON market_metrics (sort_variable, quantile_bucket);
```

### Metrics

| Metric | Description |
|---|---|
| `oddlot_rate` | Percentage of trades executed in sub-round-lot sizes (<100 shares) -- retail activity proxy |
| `oddlot_volume` | Total share volume traded in odd-lot orders |
| `hidden_rate` | Percentage of volume executed via non-displayed orders -- institutional activity proxy |
| `hidden_volume` | Total share volume traded through hidden or iceberg orders |
| `cancel_to_trade` | Order cancellations divided by executed trades -- algorithmic activity indicator |
| `trade_volume` | Total shares traded -- core liquidity measure |

---

## Setup

### Prerequisites

- Python 3.10 or higher
- A HuggingFace account with a free API token ([huggingface.co/settings/tokens](https://huggingface.co/settings/tokens))

### 1. Clone the repository

```bash
git clone https://github.com/your-username/market-microstructure-dashboard.git
cd market-microstructure-dashboard
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate       # macOS / Linux
venv\Scripts\activate          # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
HF_TOKEN=hf_your_token_here
DATA_DIR=./data
DB_NAME=advanced_microstructure.db
```

### 5. Add raw data

Place SEC microstructure CSV files in the `data/` directory.
Files must follow this naming convention:

```
{quantile_type}_{metric_name}_{asset_class}.csv
```

Examples:
```
decile_oddlot_rate_stock.csv
quartile_hidden_rate_etp.csv
decile_cancel_to_trade_stock.csv
```

### 6. Run the ETL pipeline

```bash
python etl.py

# Specify a custom data directory if needed:
python etl.py --data-dir /path/to/csv/folder
```

### 7. Launch the dashboard

```bash
python run_dashboard.py
```

The dashboard opens at `http://localhost:8501`.

---

## AI Chat Assistant

The assistant supports the following question types:

| Question Type | Example |
|---|---|
| Definition | "What does hidden rate mean?" |
| Comparison | "Compare oddlot rates for etp vs stocks" |
| Correlation | "What is the correlation between volatility and cancel to trade?" |
| Ranking | "Which quantile bucket has the highest hidden rate for stocks?" |
| Summary | "Summarize the data for ETPs" |

The assistant follows a two-step process:
1. A SQL aggregation retrieves the relevant data from SQLite
2. Mistral-7B-Instruct (via HuggingFace Inference API) generates a plain-language summary

If the API is unavailable, the formatted SQL results are returned directly.

---

## Verification

```bash
# Validate the ETL pipeline against a sample file
python etl.py --data-dir ./tests/sample_data

# Verify schema validation loads correctly
python -c "from schemas import MarketMetricSchema; print('Schema OK')"

# Confirm config resolves environment variables
python -c "from config import DB_NAME, DATA_DIR; print(DB_NAME, DATA_DIR)"
```

---

## Design Notes

**SQLite over PostgreSQL** -- the dataset fits within SQLite's performance
envelope for a single-user analytical workload. The dual-index strategy keeps
query latency low without requiring a separate server process. Migrating to
PostgreSQL requires changing only the connection string in `config.py`.

**Pattern-matching over a LangGraph agent** -- the HuggingFace free inference
tier does not support tool or function calling, which LangGraph requires.
The pattern-matching router handles the same analytical question types
(definitions, comparisons, correlations, rankings) without depending on
paid APIs or local GPU hardware. The `call_llm()` function in `app.py`
accepts any OpenAI-compatible endpoint, so switching providers requires
changing one URL.

**log1p transformation** -- volume-based microstructure metrics have strong
right skew and occasional extreme values. The `log1p` transformation
compresses the dynamic range, which improves chart readability and downstream
model performance.

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Commit your changes: `git commit -m "feat: describe your change"`
4. Push to the branch: `git push origin feature/your-feature-name`
5. Open a pull request

All new code should include type hints and docstrings consistent with the
existing codebase.

---

## License

MIT License. See `LICENSE` for details.

---

## Author

Arya -- financial data engineering and analytical dashboard development.
