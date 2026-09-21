#!/usr/bin/env python3

import json
from pathlib import Path

RAW = Path(__file__).resolve().parent / "reports/hw03/raw"
TECHNIQUES = ["token", "semantic", "sentence_window"]


def main():
    records = json.loads((RAW / "retrieval_records.json").read_text())
    chunk_stats = json.loads((RAW / "chunk_stats.json").read_text())

    table = {}
    for tech in TECHNIQUES:
        recs = [r for r in records if r["technique"] == tech]
        top1 = [r["results"][0]["cosine_sim"] for r in recs]
        mean_at_k = [sum(x["cosine_sim"] for x in r["results"]) / len(r["results"]) for r in recs]
        recall = [r["expected_source_file"] in {x["source_file"] for x in r["results"]} for r in recs]
        latency = [r["latency_ms"] for r in recs]
        table[tech] = {
            "n_chunks": chunk_stats[tech]["n_chunks"],
            "avg_chunk_len": chunk_stats[tech]["avg_chunk_len"],
            "top1_cosine_mean": round(sum(top1) / len(top1), 4),
            "mean_at_k_cosine_mean": round(sum(mean_at_k) / len(mean_at_k), 4),
            "recall_at_k": round(sum(recall) / len(recall), 3),
            "mean_retrieval_latency_ms": round(sum(latency) / len(latency), 2),
        }

    print(f"{len(records)} records ({len(records) // len(TECHNIQUES)} questions x {len(TECHNIQUES)} techniques)\n")
    print(f"{'Technique':<17}{'Chunks':<8}{'AvgLen':<9}{'Top-1':<8}{'Mean@k':<8}{'Recall@k':<10}{'Latency(ms)'}")
    for tech, v in table.items():
        print(f"{tech:<17}{v['n_chunks']:<8}{v['avg_chunk_len']:<9}{v['top1_cosine_mean']:<8}"
              f"{v['mean_at_k_cosine_mean']:<8}{v['recall_at_k']:<10}{v['mean_retrieval_latency_ms']}")

    (RAW / "summary_recomputed.json").write_text(json.dumps(table, indent=2))

    saved = json.loads((RAW / "summary.json").read_text())
    print("\nmatches summary.json written during the run:", table == saved)


if __name__ == "__main__":
    main()
