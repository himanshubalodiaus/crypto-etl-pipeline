# Crypto Market ETL Pipeline

An automated **ETL pipeline** that ingests cryptocurrency market data, transforms it into analytical metrics, validates it, and loads it into PostgreSQL — with an interactive **Streamlit dashboard** on top.

Built end-to-end in Python: extract → transform → validate → load, with data-quality safeguards and idempotent, re-runnable loads.

**🔗 Live dashboard:** [View live](https://crypto-etl-pipeline-ia96b46bueawgqosihpdcd.streamlit.app/) · **📊 Data source:** [CoinGecko API](https://www.coingecko.com/en/api)

## Screenshot

![Dashboard](docs/dashboard.png)



## What it does

The pipeline pulls price, market-cap, and volume data for 10 major cryptocurrencies, computes derived analytics (moving averages, daily returns, rolling volatility), checks the data is sane, and stores one clean row per coin per day in a Postgres database. A Streamlit dashboard reads from that database to show price history with moving-average overlays, volatility trends, and a table of daily movers.

## Architecture

```
CoinGecko API
     │
     ▼
  Extract  ──►  Transform  ──►  Validate  ──►  Load  ──►  PostgreSQL
 (fetch +      (clean +        (quality       (idempotent      │
  retry +       derive          gates)         upsert)         ▼
  cache)        metrics)                                  Streamlit
                                                          dashboard
```

Each stage is a focused, independently testable module.

## Tech stack

| Layer | Tools |
|---|---|
| Language | Python 3.11+ |
| Extraction | `requests` (retry + backoff + caching) |
| Transformation | `pandas` (rolling windows, grouped metrics) |
| Storage | PostgreSQL via `SQLAlchemy` + `psycopg2` |
| Dashboard | `Streamlit` + `Plotly` |
| Config / secrets | `python-dotenv` (env-driven, no secrets in code) |

## Pipeline stages

- **`extract.py`** — fetches a current market snapshot from CoinGecko, with automatic retry/backoff on transient failures and local caching to respect rate limits.
- **`backfill.py`** — one-time historical load; pulls 90 days of price history per coin so analytics work immediately.
- **`transform.py`** — collapses to one row per coin per day and derives metrics: daily returns, 7- and 30-day moving averages, and 7-day rolling volatility (all computed per-coin).
- **`validate.py`** — a quality gate that blocks bad data before storage (missing/negative prices, duplicate days, future timestamps), separating hard failures from soft warnings.
- **`load.py`** — writes to Postgres with an **idempotent upsert** keyed on `(coin_id, captured_at)`, so re-running the pipeline never creates duplicates.
- **`dashboard.py`** — Streamlit + Plotly dashboard reading from the database.

## Getting started

### 1. Clone and install

```bash
git clone https://github.com/<your-username>/crypto-etl-pipeline.git
cd crypto-etl-pipeline
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Set up the database

Create a free PostgreSQL database (e.g. [Neon](https://neon.tech) or [Supabase](https://supabase.com)) and copy the connection string.

Create a `.env` file in the project root:

```
DATABASE_URL=postgresql://user:password@host/dbname
```

> `.env` is git-ignored — your credentials never leave your machine.

### 3. Run the pipeline

```bash
python load.py          # backfill → transform → validate → load
```

Run it again — the row count won't grow (idempotent upsert).

### 4. Launch the dashboard

```bash
streamlit run dashboard.py
```

## Project structure

```
crypto-etl-pipeline/
├── extract.py         # E — fetch current snapshot
├── backfill.py        # historical backfill
├── transform.py       # T — derive metrics
├── validate.py        # data-quality gate
├── load.py            # L — idempotent upsert to Postgres
├── dashboard.py       # Streamlit dashboard
├── requirements.txt
├── .env               # (git-ignored) DATABASE_URL
├── .gitignore
└── docs/
    └── dashboard.png
```

## Design highlights

- **Idempotent by design** — safe to run on a schedule; the composite primary key plus `ON CONFLICT DO UPDATE` guarantees no duplicate rows.
- **Data quality as a first-class stage** — explicit validation blocks malformed data before it reaches storage.
- **Separation of concerns** — extract, transform, validate, and load are independent modules, each testable in isolation.
- **Secrets kept out of source** — all credentials via environment variables.

## Roadmap

- [ ] Schedule automated runs (GitHub Actions cron)
- [ ] Containerise with Docker + docker-compose
- [ ] Orchestrate with Apache Airflow (extract → transform → validate → load as a DAG)
- [ ] CI pipeline: automated tests + linting on every push
- [x] Deploy dashboard publicly (Streamlit Community Cloud)

## License

MIT