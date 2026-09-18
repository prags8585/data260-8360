#!/usr/bin/env python3
"""HW3 Part 2: compare three LlamaIndex chunking techniques (Token, Semantic,
Sentence-window) on a retrieval-only RAG pipeline over the DOMAIN_ID=0 corpus.

For each technique: chunk the corpus, build an in-memory VectorStoreIndex
(SimpleVectorStore) with a local HuggingFace sentence embedding model, then
for each of the 5 questions in questions.yaml run retrieval and record, per
retrieved chunk: store_score, an explicitly recomputed cosine similarity
between the query embedding and that chunk's embedding, chunk length, and a
160-char preview. Saves raw per-query/per-technique records to raw/, and a
machine-computed summary table matching the report's required metrics.
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import yaml
from llama_index.core import Document, Settings, VectorStoreIndex
from llama_index.core.node_parser import (
    SemanticSplitterNodeParser,
    SentenceWindowNodeParser,
    TokenTextSplitter,
)
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

ROOT = Path(__file__).resolve().parent
CORPUS_DIR = ROOT / "corpus/hw03"
RAW_DIR = ROOT / "reports/hw03/raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K = 5

# Token chunking: 256 tokens per chunk is small enough to keep chunks focused
# on a single policy/requirement, with 32 tokens (12.5%) overlap so a fact
# split across a chunk boundary is still whole in at least one chunk.
TOKEN_CHUNK_SIZE = 256
TOKEN_CHUNK_OVERLAP = 32

# Semantic: buffer_size=1 groups single sentences before measuring embedding
# distance between groups; breakpoint_percentile_threshold=95 (the LlamaIndex
# default) only splits where the semantic distance to the next group is in
# the top 5% most dissimilar -- i.e. splits only at strong topic changes.
SEMANTIC_BUFFER_SIZE = 1
SEMANTIC_BREAKPOINT_PERCENTILE = 95

# Sentence-window: each node is a single sentence; window=3 attaches the 3
# sentences before and after as metadata, so embedding happens on a precise
# sentence but generation-time context (not used here, retrieval-only) would
# still see the surrounding paragraph.
SENTENCE_WINDOW_SIZE = 3


def load_corpus() -> list[Document]:
    docs = []
    for path in sorted(CORPUS_DIR.glob("*.txt")):
        text = path.read_text()
        docs.append(Document(text=text, metadata={"file_name": path.name}))
    return docs


def build_token_index(docs, embed_model):
    splitter = TokenTextSplitter(chunk_size=TOKEN_CHUNK_SIZE, chunk_overlap=TOKEN_CHUNK_OVERLAP)
    nodes = splitter.get_nodes_from_documents(docs)
    index = VectorStoreIndex(nodes, embed_model=embed_model)
    return index, nodes


def build_semantic_index(docs, embed_model):
    splitter = SemanticSplitterNodeParser(
        buffer_size=SEMANTIC_BUFFER_SIZE,
        breakpoint_percentile_threshold=SEMANTIC_BREAKPOINT_PERCENTILE,
        embed_model=embed_model,
    )
    nodes = splitter.get_nodes_from_documents(docs)
    index = VectorStoreIndex(nodes, embed_model=embed_model)
    return index, nodes


def build_sentence_window_index(docs, embed_model):
    splitter = SentenceWindowNodeParser.from_defaults(
        window_size=SENTENCE_WINDOW_SIZE,
        window_metadata_key="window",
        original_text_metadata_key="original_text",
    )
    nodes = splitter.get_nodes_from_documents(docs)
    index = VectorStoreIndex(nodes, embed_model=embed_model)
    return index, nodes


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def retrieve_and_analyze(index, embed_model, technique: str, question_id: str, query: str, k: int = TOP_K, verbose: bool = True):
    query_vec = np.array(embed_model.get_query_embedding(query))

    retriever = index.as_retriever(similarity_top_k=k)
    start = time.perf_counter()
    retrieved = retriever.retrieve(query)
    latency_ms = (time.perf_counter() - start) * 1000

    doc_vecs = []
    rows = []
    for rank, node_with_score in enumerate(retrieved, start=1):
        node = node_with_score.node
        chunk_text = node.get_content()
        doc_vec = np.array(embed_model.get_text_embedding(chunk_text))
        doc_vecs.append(doc_vec)
        sim = cosine_sim(query_vec, doc_vec)
        rows.append({
            "rank": rank,
            "store_score": round(float(node_with_score.score), 6) if node_with_score.score is not None else None,
            "cosine_sim": round(sim, 6),
            "chunk_len": len(chunk_text),
            "source_file": node.metadata.get("file_name"),
            "preview": chunk_text[:160].replace("\n", " "),
        })

    doc_matrix = np.stack(doc_vecs) if doc_vecs else np.zeros((0, len(query_vec)))

    if verbose:
        print(f"\n=== [{technique}] {question_id}: {query.strip()[:80]} ===")
        print(f"query embedding dim: {query_vec.shape[0]}, first 8 values: {query_vec[:8].round(4).tolist()}")
        print(f"query vector shape: {query_vec.shape}, stacked doc vectors shape: {doc_matrix.shape}")
        print(f"{'rank':<5}{'store_score':<13}{'cosine_sim':<12}{'chunk_len':<10}{'source_file':<45}preview")
        for r in rows:
            print(f"{r['rank']:<5}{str(r['store_score']):<13}{r['cosine_sim']:<12}{r['chunk_len']:<10}{str(r['source_file']):<45}{r['preview']}")
        print(f"retrieval latency: {latency_ms:.2f} ms")

    return {
        "technique": technique,
        "question_id": question_id,
        "query": query,
        "query_embed_dim": int(query_vec.shape[0]),
        "query_embed_first8": query_vec[:8].round(6).tolist(),
        "latency_ms": round(latency_ms, 3),
        "results": rows,
    }


def chunk_stats(nodes):
    lengths = [len(n.get_content()) for n in nodes]
    return {"n_chunks": len(nodes), "avg_chunk_len": round(sum(lengths) / len(lengths), 1) if lengths else 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=TOP_K)
    args = parser.parse_args()

    print(f"=== {time.strftime('%Y-%m-%d %H:%M:%S %Z')} ===")
    print(f"$ python rag_chunking_comparison.py --k {args.k}")

    questions = yaml.safe_load((ROOT / "questions.yaml").read_text())["questions"]

    print("\nLoading embedding model:", EMBED_MODEL_NAME)
    embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL_NAME)
    Settings.embed_model = embed_model
    Settings.llm = None  # retrieval-only, no generation

    docs = load_corpus()
    print(f"Loaded {len(docs)} corpus documents, {sum(len(d.text) for d in docs)} total chars")

    builders = {
        "token": build_token_index,
        "semantic": build_semantic_index,
        "sentence_window": build_sentence_window_index,
    }

    all_records = []
    summary = {}

    for technique, builder in builders.items():
        print(f"\n{'=' * 70}\nTECHNIQUE: {technique}\n{'=' * 70}")
        t0 = time.perf_counter()
        index, nodes = builder(docs, embed_model)
        build_ms = (time.perf_counter() - t0) * 1000
        stats = chunk_stats(nodes)
        print(f"Chunked into {stats['n_chunks']} nodes (avg len {stats['avg_chunk_len']} chars) in {build_ms:.0f} ms")

        technique_records = []
        for q in questions:
            rec = retrieve_and_analyze(index, embed_model, technique, q["id"], q["question"], k=args.k)
            rec["expected_source_file"] = q["expected_source_file"]
            top_k_sources = {r["source_file"] for r in rec["results"]}
            rec["recall_hit"] = q["expected_source_file"] in top_k_sources
            technique_records.append(rec)
            all_records.append(rec)

        top1_cosines = [r["results"][0]["cosine_sim"] for r in technique_records if r["results"]]
        mean_at_k_cosines = [
            sum(x["cosine_sim"] for x in r["results"]) / len(r["results"])
            for r in technique_records if r["results"]
        ]
        recall_hits = [r["recall_hit"] for r in technique_records]
        latencies = [r["latency_ms"] for r in technique_records]

        summary[technique] = {
            "n_chunks": stats["n_chunks"],
            "avg_chunk_len": stats["avg_chunk_len"],
            "top1_cosine_mean": round(sum(top1_cosines) / len(top1_cosines), 4),
            "mean_at_k_cosine_mean": round(sum(mean_at_k_cosines) / len(mean_at_k_cosines), 4),
            "recall_at_k": round(sum(recall_hits) / len(recall_hits), 3),
            "mean_retrieval_latency_ms": round(sum(latencies) / len(latencies), 2),
        }

    raw_path = RAW_DIR / "retrieval_records.json"
    raw_path.write_text(json.dumps(all_records, indent=2))
    print(f"\nSaved {len(all_records)} per-query/per-technique records to {raw_path}")

    import csv
    csv_path = RAW_DIR / "retrieval_records.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["technique", "question_id", "rank", "store_score", "cosine_sim", "chunk_len", "source_file", "expected_source_file", "recall_hit", "latency_ms", "preview"])
        for rec in all_records:
            for r in rec["results"]:
                writer.writerow([rec["technique"], rec["question_id"], r["rank"], r["store_score"], r["cosine_sim"], r["chunk_len"], r["source_file"], rec["expected_source_file"], rec["recall_hit"], rec["latency_ms"], r["preview"]])
    print(f"Saved flat CSV to {csv_path}")

    summary_path = RAW_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"\n{'=' * 70}\nSUMMARY\n{'=' * 70}")
    print(json.dumps(summary, indent=2))
    print(f"\nSaved summary to {summary_path}")
    print(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S %Z')} completed ===")


if __name__ == "__main__":
    main()
