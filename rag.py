#!/usr/bin/env python3

import json
import time
from pathlib import Path

import numpy as np
from langchain_ollama import ChatOllama
from llama_index.core import Document, Settings, VectorStoreIndex
from llama_index.core.node_parser import TokenTextSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

ROOT = Path(__file__).resolve().parent
CORPUS_DIR = ROOT / "corpus/hw03"
RAW_DIR = ROOT / "reports/hw04/raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
LLM_MODEL = "qwen3:8b"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K = 3

REFUSAL = "I cannot answer this question from the provided documents."

QUESTIONS = [
    {
        "id": "q1", "category": "single chunk",
        "question": "What is the late registration fee assessed after the census date, and when does it apply?",
        "expected_source": "registration_and_attendance.txt",
        "answer_markers": ["$200.00"],
    },
    {
        "id": "q2", "category": "needs two chunks",
        "question": "What are the two specialization tracks in SJSU's MS in Applied Data Intelligence program, and which DATA course numbers belong to each?",
        "expected_source": "applied_data_intelligence_ms_program.txt",
        "answer_markers": ["Analytics Technologies", "Data Engineering"],
    },
    {
        "id": "q3", "category": "similar info across documents",
        "question": "What is the minimum GPA a student must maintain to stay in good academic standing?",
        "expected_source": "graduate_policies_procedures.txt",
        "answer_markers": ["3.0"],
    },
    {
        "id": "q4", "category": "ambiguous",
        "question": "What is the deadline to add a class?",
        "expected_source": "adding_dropping_classes.txt",
        "answer_markers": [],  # no single correct marker -- multiple valid deadlines exist; judged manually
    },
    {
        "id": "q5", "category": "not in the documents",
        "question": "What is the tuition refund policy for withdrawing in Fall 2026?",
        "expected_source": None,
        "answer_markers": [],
        "must_refuse": True,
    },
    {
        "id": "q6", "category": "unrelated",
        "question": "What is the boiling point of water at sea level, in Celsius?",
        "expected_source": None,
        "answer_markers": [],
        "must_refuse": True,
    },
]


def load_corpus() -> list[Document]:
    docs = []
    for path in sorted(CORPUS_DIR.glob("*.txt")):
        text = path.read_text()
        docs.append(Document(text=text, metadata={"file_name": path.name}))
    return docs


def build_index(docs, embed_model):
    splitter = TokenTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    nodes = splitter.get_nodes_from_documents(docs)
    for i, node in enumerate(nodes):
        node.metadata["chunk_id"] = f"{node.metadata.get('file_name')}#{i}"
    index = VectorStoreIndex(nodes, embed_model=embed_model)
    return index, nodes


def retrieve(index, query: str, k: int, verbose: bool = True) -> list[dict]:
    retriever = index.as_retriever(similarity_top_k=k)
    retrieved = retriever.retrieve(query)
    rows = [{
        "chunk_id": n.node.metadata.get("chunk_id"),
        "source": n.node.metadata.get("file_name"),
        "score": round(float(n.score), 4) if n.score is not None else None,
        "text": n.node.get_content(),
    } for n in retrieved]
    if verbose:
        print(f"  retrieved top-{k}:")
        for r in rows:
            preview = r["text"][:100].replace("\n", " ")
            print(f"    [{r['chunk_id']}] score={r['score']} source={r['source']}: {preview}")
    return rows


def dedupe_and_filter(rows: list[dict], top_k: int) -> list[dict]:
    seen_prefixes = set()
    kept = []
    top_score = rows[0]["score"] if rows else 0
    for r in rows:
        prefix = r["text"][:80].strip()
        if prefix in seen_prefixes:
            continue
        if top_score and r["score"] < top_score - 0.15:
            continue
        seen_prefixes.add(prefix)
        kept.append(r)
    return kept[:top_k]


def call_llm(llm, system: str, user: str) -> str:
    response = llm.invoke([("system", system), ("user", user)])
    return response.content.strip()


def no_rag(llm, question: str) -> dict:
    system = "You are a helpful assistant. Answer the user's question directly and concisely."
    answer = call_llm(llm, system, question)
    return {"config": "A_no_rag", "retrieved": [], "answer": answer}


def basic_rag(llm, index, question: str, k: int = TOP_K) -> dict:
    rows = retrieve(index, question, k)
    context = "\n\n".join(r["text"] for r in rows)
    system = "Answer the user's question using the context below."
    user = f"Context:\n{context}\n\nQuestion: {question}"
    answer = call_llm(llm, system, user)
    return {"config": "B_basic_rag", "retrieved": rows, "answer": answer}


def context_engineered_rag(llm, index, question: str, k: int = TOP_K, k_candidates: int = 8) -> dict:
    candidates = retrieve(index, question, k_candidates, verbose=False)
    survivors = dedupe_and_filter(candidates, k)
    print(f"  after dedupe/filter, kept {len(survivors)} of {len(candidates)} candidates:")
    for r in survivors:
        preview = r["text"][:100].replace("\n", " ")
        print(f"    [{r['chunk_id']}] score={r['score']} source={r['source']}: {preview}")

    labeled = "\n\n".join(f"[Source {i+1}: {r['source']}]\n{r['text']}" for i, r in enumerate(survivors))
    system = (
        "Answer ONLY using the numbered sources below. Cite the source number(s) you used, "
        "like [Source 1]. Do not use outside knowledge. If the sources do not contain the "
        f"answer, reply with EXACTLY this sentence and nothing else: \"{REFUSAL}\""
    )
    user = f"Sources:\n{labeled}\n\nQuestion: {question}"
    answer = call_llm(llm, system, user)
    return {"config": "C_context_engineered", "retrieved": survivors, "answer": answer}


def evaluate(q: dict, result: dict) -> dict:
    answer = result["answer"]
    retrieved_sources = {r["source"] for r in result["retrieved"]}
    correct_retrieval = (
        None if q["expected_source"] is None
        else q["expected_source"] in retrieved_sources
    )
    correct_answer = (
        all(m.lower() in answer.lower() for m in q["answer_markers"])
        if q["answer_markers"] else None
    )
    refused = REFUSAL.lower() in answer.lower()
    refused_when_needed = refused if q.get("must_refuse") else (None if not q.get("must_refuse") else False)
    grounded = None
    if result["config"] == "C_context_engineered":
        has_citation = "[source" in answer.lower()
        grounded = refused or has_citation
    return {
        "correct_retrieval": correct_retrieval,
        "correct_answer": correct_answer,
        "grounded": grounded,
        "refused": refused,
        "refused_when_needed": refused if q.get("must_refuse") else None,
    }


def run_k_sweep(llm, index, question: dict, ks=(1, 3, 5)):
    print(f"\n{'='*70}\nK-SWEEP on {question['id']}: {question['question']}\n{'='*70}")
    sweep_results = []
    for k in ks:
        print(f"\n--- k={k} ---")
        result = context_engineered_rag(llm, index, question["question"], k=k, k_candidates=max(8, k + 3))
        print(f"  answer: {result['answer']}")
        ev = evaluate(question, result)
        sweep_results.append({"k": k, "answer": result["answer"], "retrieved": result["retrieved"], **ev})
    return sweep_results


def main():
    print(f"=== {time.strftime('%Y-%m-%d %H:%M:%S %Z')} ===")
    print(f"Embedding model: {EMBED_MODEL_NAME}")
    embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL_NAME)
    Settings.embed_model = embed_model

    print(f"LLM: {LLM_MODEL} (via Ollama, temperature=0.0, reasoning=False)")
    llm = ChatOllama(model=LLM_MODEL, temperature=0.0, reasoning=False)

    docs = load_corpus()
    print(f"Loaded {len(docs)} corpus documents, {sum(len(d.text) for d in docs)} total chars")
    index, nodes = build_index(docs, embed_model)
    print(f"Chunked into {len(nodes)} nodes (chunk_size={CHUNK_SIZE}, chunk_overlap={CHUNK_OVERLAP})")

    all_results = []
    for q in QUESTIONS:
        print(f"\n{'='*70}\n{q['id'].upper()} [{q['category']}]: {q['question']}\n{'='*70}")

        print("\n-- (A) No RAG --")
        rA = no_rag(llm, q["question"])
        print(f"  answer: {rA['answer']}")
        evA = evaluate(q, rA)

        print("\n-- (B) Basic RAG --")
        rB = basic_rag(llm, index, q["question"])
        print(f"  answer: {rB['answer']}")
        evB = evaluate(q, rB)

        print("\n-- (C) Context-engineered RAG --")
        rC = context_engineered_rag(llm, index, q["question"])
        print(f"  answer: {rC['answer']}")
        evC = evaluate(q, rC)

        for result, ev in [(rA, evA), (rB, evB), (rC, evC)]:
            all_results.append({
                "question_id": q["id"], "category": q["category"], "question": q["question"],
                "config": result["config"], "answer": result["answer"],
                "retrieved": result["retrieved"], **ev,
            })

    (RAW_DIR / "rag_results.json").write_text(json.dumps(all_results, indent=2))
    print(f"\nSaved {len(all_results)} question/config records to {RAW_DIR / 'rag_results.json'}")

    q2 = next(q for q in QUESTIONS if q["id"] == "q2")
    sweep = run_k_sweep(llm, index, q2)
    (RAW_DIR / "k_sweep_results.json").write_text(json.dumps(sweep, indent=2))
    print(f"\nSaved k-sweep results to {RAW_DIR / 'k_sweep_results.json'}")

    print(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S %Z')} completed ===")


if __name__ == "__main__":
    main()
