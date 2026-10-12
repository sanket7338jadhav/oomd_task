# OOMD: SQL vs NoSQL Document Model Comparison

A reproducible OOMD assignment project comparing a relational SQL model and a simple JSON document model for an e-commerce order-tracking use case.

## What it measures

- Dataset population time (ms)
- Status-filter query latency (ms)
- Update latency for approximately 1% of records (ms)
- SQLite database page footprint proxy (KB)
- Workloads at 1,000, 5,000, and 10,000 records by default
- Median of five repeated runs by default

## Important interpretation

This project uses SQLite for both representations:
- **Approach A:** normalized relational tables (`users`, `orders`)
- **Approach B:** one JSON document per record with an embedded `order` object

This makes the experiment easy to reproduce without installing a database server. It is a comparison of data-modeling approaches on SQLite, not a direct benchmark of PostgreSQL/MySQL against MongoDB.

The footprint metric is `PRAGMA page_count × PRAGMA page_size`; it is not operating-system process memory.

## Requirements

- Python 3.9+
- SQLite with JSON functions
- pandas
- matplotlib

Install packages:

```bash
python -m pip install -r requirements.txt
```

## Run locally

```bash
python benchmark.py
```

Choose different workloads:

```bash
python benchmark.py --sizes 500 1000 5000 10000 --repeats 5
```

Outputs are written to `results/`:
- `performance_results.csv`
- `comparison_matrix.csv`
- `query_latency.png`
- `population_time.png`
- `update_latency.png`
- `database_footprint.png`

## Run in Jupyter Notebook

1. Open `OOMD_Comparison.ipynb` in Jupyter or upload it to Google Colab.
2. Run the cells from top to bottom.
3. The notebook prints the evaluation matrix and displays graphs.
4. Download the generated CSV and graph files if needed.

## Data generation

The dataset is synthetic and deterministic. Each record has customer details and one associated order with a date, status, and total. The simplified one-order-per-customer setup keeps the two representations comparable for the selected workloads.

## Limitations

- In-memory databases exclude disk and network latency.
- Only one query pattern and one update pattern are measured.
- There is no concurrency, replication, sharding, or failure-recovery workload.
- Results vary with hardware, SQLite version, indexing, and system load.
- Five-run medians reduce noise but do not prove statistical significance.

## Suggested repository description

"An OOMD experimental project comparing SQL relational tables with a simple JSON document model using a reproducible e-commerce order-tracking workload, performance tables, and graphs."
