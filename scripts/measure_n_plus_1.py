#!/usr/bin/env python3
import csv
import json
import statistics
import time
from pathlib import Path

import requests

BASE = "http://localhost:8260/api/perf/courses"
PAGE_SIZES = [10, 50, 200]
MODES = ["naive", "fixed"]
N_REQUESTS = 30

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "reports/hw04/raw"
RAW.mkdir(parents=True, exist_ok=True)


def percentile(values, p):
    values = sorted(values)
    k = (len(values) - 1) * (p / 100)
    f, c = int(k), min(int(k) + 1, len(values) - 1)
    if f == c:
        return values[f]
    return values[f] + (values[c] - values[f]) * (k - f)


def main():
    records = []
    for page_size in PAGE_SIZES:
        for mode in MODES:
            print(f"\n{page_size} / {mode}:")
            for i in range(N_REQUESTS):
                start = time.perf_counter()
                resp = requests.get(BASE, params={"page": 1, "page_size": page_size, "mode": mode})
                latency_ms = (time.perf_counter() - start) * 1000
                resp.raise_for_status()
                sql_stmts = int(resp.headers["X-SQL-Query-Count"])
                records.append({
                    "page_size": page_size, "mode": mode, "request_num": i + 1,
                    "sql_stmts": sql_stmts, "latency_ms": round(latency_ms, 3),
                })
            latencies = [r["latency_ms"] for r in records if r["page_size"] == page_size and r["mode"] == mode]
            stmts = [r["sql_stmts"] for r in records if r["page_size"] == page_size and r["mode"] == mode]
            print(f"  sql_stmts={stmts[0]} (constant)  "
                  f"p50={percentile(latencies,50):.2f}ms  p95={percentile(latencies,95):.2f}ms  p99={percentile(latencies,99):.2f}ms")

    raw_path = RAW / "n_plus_1_records.json"
    raw_path.write_text(json.dumps(records, indent=2))
    csv_path = RAW / "n_plus_1_records.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["page_size", "mode", "request_num", "sql_stmts", "latency_ms"])
        writer.writeheader()
        writer.writerows(records)
    print(f"\nSaved {len(records)} raw records to {raw_path} and {csv_path}")

    summary = {}
    for page_size in PAGE_SIZES:
        for mode in MODES:
            subset = [r for r in records if r["page_size"] == page_size and r["mode"] == mode]
            latencies = [r["latency_ms"] for r in subset]
            summary[f"{page_size}_{mode}"] = {
                "page_size": page_size,
                "mode": mode,
                "sql_stmts_per_req": subset[0]["sql_stmts"],
                "p50_ms": round(percentile(latencies, 50), 2),
                "p95_ms": round(percentile(latencies, 95), 2),
                "p99_ms": round(percentile(latencies, 99), 2),
            }

    summary_path = RAW / "n_plus_1_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    print(f"\n{'Page size':<12}{'Version':<10}{'SQL stmts/req':<16}{'p50 (ms)':<12}{'p95 (ms)':<12}{'p99 (ms)'}")
    for v in summary.values():
        print(f"{v['page_size']:<12}{v['mode']:<10}{v['sql_stmts_per_req']:<16}{v['p50_ms']:<12}{v['p95_ms']:<12}{v['p99_ms']}")

    print("\nSpeed-up (naive p50 / fixed p50) by page size:")
    for page_size in PAGE_SIZES:
        naive = summary[f"{page_size}_naive"]["p50_ms"]
        fixed = summary[f"{page_size}_fixed"]["p50_ms"]
        print(f"  page_size={page_size}: naive {naive}ms / fixed {fixed}ms = {naive/fixed:.2f}x faster")

    print(f"\nSaved summary to {summary_path}")


if __name__ == "__main__":
    main()
