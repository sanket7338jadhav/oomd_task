"""
OOMD Assignment: SQL vs NoSQL Document Model
Use case: E-commerce order tracking

Run:
    python benchmark.py
    python benchmark.py --sizes 1000 5000 10000 --repeats 5

Outputs:
    results/performance_results.csv
    results/query_latency.png
    results/population_time.png
    results/update_latency.png
    results/database_footprint.png

Note:
This is a model-level comparison using SQLite relational tables and SQLite JSON
documents. It is NOT a direct benchmark of PostgreSQL/MySQL versus MongoDB.
"""
import argparse
import json
import platform
import sqlite3
import statistics
import time
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


STATUSES = ["pending", "shipped", "delivered", "cancelled"]
CITIES = ["Pune", "Mumbai", "Nashik", "Nagpur"]


def build_and_populate(model: str, n: int):
    """Create a fresh in-memory database and populate the selected model."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA journal_mode=MEMORY")
    conn.execute("PRAGMA synchronous=OFF")

    start = time.perf_counter()

    if model == "SQL":
        conn.executescript("""
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                city TEXT NOT NULL
            );

            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                order_date TEXT NOT NULL,
                status TEXT NOT NULL,
                total REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE INDEX idx_orders_status ON orders(status);
            CREATE INDEX idx_orders_user ON orders(user_id);
        """)

        users = [
            (i, f"User {i}", f"user{i}@example.com", CITIES[i % len(CITIES)])
            for i in range(1, n + 1)
        ]
        orders = [
            (
                i,
                i,  # one order per user for this controlled benchmark
                f"2026-09-{(i % 28) + 1:02d}",
                STATUSES[i % len(STATUSES)],
                round(100 + (i % 100) * 13.37, 2),
            )
            for i in range(1, n + 1)
        ]
        conn.executemany("INSERT INTO users VALUES (?, ?, ?, ?)", users)
        conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", orders)

    elif model == "Document":
        conn.execute("""
            CREATE TABLE documents (
                doc_id INTEGER PRIMARY KEY,
                body TEXT NOT NULL
            )
        """)

        docs = []
        for i in range(1, n + 1):
            document = {
                "user_id": i,
                "name": f"User {i}",
                "email": f"user{i}@example.com",
                "city": CITIES[i % len(CITIES)],
                "order": {
                    "order_id": i,
                    "order_date": f"2026-09-{(i % 28) + 1:02d}",
                    "status": STATUSES[i % len(STATUSES)],
                    "total": round(100 + (i % 100) * 13.37, 2),
                },
            }
            docs.append((i, json.dumps(document, separators=(",", ":"))))

        conn.executemany("INSERT INTO documents VALUES (?, ?)", docs)
        conn.execute("""
            CREATE INDEX idx_documents_status
            ON documents(json_extract(body, '$.order.status'))
        """)
    else:
        conn.close()
        raise ValueError("model must be 'SQL' or 'Document'")

    conn.commit()
    population_ms = (time.perf_counter() - start) * 1000
    return conn, population_ms


def run_query(conn, model: str):
    """Return the same logical fields from either model."""
    start = time.perf_counter()

    if model == "SQL":
        rows = conn.execute("""
            SELECT o.order_id, u.name, o.status, o.total
            FROM orders AS o
            JOIN users AS u ON u.user_id = o.user_id
            WHERE o.status = 'shipped'
        """).fetchall()
    else:
        rows = conn.execute("""
            SELECT
                json_extract(body, '$.order.order_id'),
                json_extract(body, '$.name'),
                json_extract(body, '$.order.status'),
                json_extract(body, '$.order.total')
            FROM documents
            WHERE json_extract(body, '$.order.status') = 'shipped'
        """).fetchall()

    elapsed_ms = (time.perf_counter() - start) * 1000
    return elapsed_ms, len(rows)


def update_records(conn, model: str, n: int):
    """Update approximately 1% of records, with at least one record."""
    count_to_update = max(1, n // 100)
    start = time.perf_counter()

    if model == "SQL":
        conn.execute("""
            UPDATE orders
            SET status = 'delivered'
            WHERE order_id <= ?
        """, (count_to_update,))
    else:
        conn.execute("""
            UPDATE documents
            SET body = json_set(body, '$.order.status', 'delivered')
            WHERE doc_id <= ?
        """, (count_to_update,))

    conn.commit()
    return (time.perf_counter() - start) * 1000, count_to_update


def database_footprint_kb(conn):
    """SQLite page footprint proxy; not OS process memory."""
    pages = conn.execute("PRAGMA page_count").fetchone()[0]
    page_size = conn.execute("PRAGMA page_size").fetchone()[0]
    return (pages * page_size) / 1024


def benchmark_one(model: str, n: int, repeats: int):
    measurements = {
        "population_ms": [],
        "query_ms": [],
        "update_ms": [],
        "footprint_kb": [],
        "matched_rows": [],
        "updated_records": [],
    }

    for _ in range(repeats):
        conn, population_ms = build_and_populate(model, n)
        query_ms, matched_rows = run_query(conn, model)
        update_ms, updated_records = update_records(conn, model, n)
        footprint_kb = database_footprint_kb(conn)

        measurements["population_ms"].append(population_ms)
        measurements["query_ms"].append(query_ms)
        measurements["update_ms"].append(update_ms)
        measurements["footprint_kb"].append(footprint_kb)
        measurements["matched_rows"].append(matched_rows)
        measurements["updated_records"].append(updated_records)
        conn.close()

    # Median for timing/footprint values; matched/updated counts should be stable.
    return {
        "records": n,
        "model": model,
        "repeats": repeats,
        "population_ms": statistics.median(measurements["population_ms"]),
        "query_ms": statistics.median(measurements["query_ms"]),
        "update_ms": statistics.median(measurements["update_ms"]),
        "footprint_kb": statistics.median(measurements["footprint_kb"]),
        "matched_rows": measurements["matched_rows"][0],
        "updated_records": measurements["updated_records"][0],
    }


def make_graph(df, metric, title, ylabel, filename, output_dir):
    plt.figure(figsize=(8, 5))
    for model, label in [("SQL", "Relational SQL"), ("Document", "JSON document model")]:
        subset = df[df["model"] == model].sort_values("records")
        plt.plot(subset["records"], subset[metric], marker="o", linewidth=2, label=label)

    plt.title(title)
    plt.xlabel("Number of customer-order records")
    plt.ylabel(ylabel)
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / filename, dpi=180)
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="Compare SQL and JSON document models.")
    parser.add_argument("--sizes", nargs="+", type=int, default=[1000, 5000, 10000])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", default="results")
    args = parser.parse_args()

    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    if any(n < 1 for n in args.sizes):
        parser.error("all sizes must be positive integers")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Verify that SQLite JSON functions are available before running.
    test_conn = sqlite3.connect(":memory:")
    try:
        json_ok = test_conn.execute("SELECT json_valid('{\"ok\": true}')").fetchone()[0]
    except sqlite3.OperationalError as exc:
        raise SystemExit(
            "This SQLite build does not provide JSON functions. "
            "Use a modern Python/SQLite installation."
        ) from exc
    finally:
        test_conn.close()

    print("=" * 72)
    print("OOMD EXPERIMENT: SQL vs NoSQL-STYLE JSON DOCUMENT MODEL")
    print("Use case: E-commerce order tracking")
    print(f"OS: {platform.system()} {platform.release()}")
    print(f"Python: {platform.python_version()} | SQLite: {sqlite3.sqlite_version}")
    print(f"Dataset sizes: {args.sizes} | Repetitions: {args.repeats}")
    print("JSON function check:", "PASS" if json_ok == 1 else "FAILED")
    print("=" * 72)

    rows = []
    for n in args.sizes:
        for model in ["SQL", "Document"]:
            result = benchmark_one(model, n, args.repeats)
            rows.append(result)
            print(
                f"Completed model={model:8s}, records={n:>7,}, "
                f"query={result['query_ms']:.3f} ms"
            )

    df = pd.DataFrame(rows)
    csv_path = output_dir / "performance_results.csv"
    df.to_csv(csv_path, index=False)

    print("\nPERFORMANCE RESULTS (medians)")
    display_columns = [
        "records", "model", "population_ms", "query_ms",
        "update_ms", "footprint_kb", "matched_rows", "updated_records"
    ]
    print(df[display_columns].round(3).to_string(index=False))

    print("\nCOMPARISON MATRIX")
    matrix_rows = []
    for n in args.sizes:
        sql = df[(df.records == n) & (df.model == "SQL")].iloc[0]
        doc = df[(df.records == n) & (df.model == "Document")].iloc[0]
        for metric, label, unit in [
            ("population_ms", "Population time", "ms"),
            ("query_ms", "Status-filter query latency", "ms"),
            ("update_ms", "Update latency (~1% records)", "ms"),
            ("footprint_kb", "SQLite page footprint proxy", "KB"),
        ]:
            a, b = float(sql[metric]), float(doc[metric])
            if a < b:
                observation = f"SQL lower ({(b-a)/b*100:.1f}% lower)" if b else "SQL lower"
            elif b < a:
                observation = f"Document lower ({(a-b)/a*100:.1f}% lower)" if a else "Document lower"
            else:
                observation = "Equal at displayed precision"
            matrix_rows.append({
                "Records": n,
                "Metric": f"{label} ({unit})",
                "Approach A - SQL": round(a, 3),
                "Approach B - Document": round(b, 3),
                "Observation": observation,
            })

    matrix = pd.DataFrame(matrix_rows)
    print(matrix.to_string(index=False))
    matrix.to_csv(output_dir / "comparison_matrix.csv", index=False)

    make_graph(
        df, "query_ms", "Status-filter query latency",
        "Median elapsed time (ms)", "query_latency.png", output_dir
    )
    make_graph(
        df, "population_ms", "Dataset population time",
        "Median elapsed time (ms)", "population_time.png", output_dir
    )
    make_graph(
        df, "update_ms", "Update latency for approximately 1% of records",
        "Median elapsed time (ms)", "update_latency.png", output_dir
    )
    make_graph(
        df, "footprint_kb", "SQLite database page footprint proxy",
        "Page footprint (KB)", "database_footprint.png", output_dir
    )

    print("\nFiles generated:")
    for filename in [
        "performance_results.csv", "comparison_matrix.csv",
        "query_latency.png", "population_time.png",
        "update_latency.png", "database_footprint.png"
    ]:
        print(" -", output_dir / filename)

    print("\nIMPORTANT:")
    print("These are measurements of SQLite relational tables vs SQLite JSON documents.")
    print("They do not establish that every SQL database is faster than every NoSQL database.")
    print("For your report, use the values generated on the machine where you run this code.")


if __name__ == "__main__":
    main()
