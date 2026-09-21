#!/usr/bin/env python3
"""Supplementary check: for each technique and question, does any top-5
retrieved chunk actually contain the expected answer text (not just come
from the expected file)? Marker strings are taken from questions.yaml's
expected answers. Prints the rank of the first answering chunk, or '-'."""

import yaml
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

import rag_chunking_comparison as m

MARKERS = {
    "q1": ["3.0", "disqualif"],
    "q2": ["DATA 270"],
    "q3": ["Analytics Technologies", "Data Engineering"],
    "q4": ["$200.00"],
    "q5": ["September 16, 2022"],
}


def main():
    embed = HuggingFaceEmbedding(model_name=m.EMBED_MODEL_NAME)
    questions = yaml.safe_load(open(m.ROOT / "questions.yaml"))["questions"]
    docs = m.load_corpus()
    builders = [("token", m.build_token_index), ("semantic", m.build_semantic_index),
                ("sentence_window", m.build_sentence_window_index)]
    hits = {}
    for name, builder in builders:
        index, _ = builder(docs, embed)
        retriever = index.as_retriever(similarity_top_k=m.TOP_K)
        for q in questions:
            first = "-"
            for rank, r in enumerate(retriever.retrieve(q["question"]), 1):
                text = r.node.get_content()
                if all(mk in text for mk in MARKERS[q["id"]]):
                    first = rank
                    break
            hits[(name, q["id"])] = first

    print(f"{'technique':<17}" + "".join(f"{q['id']:<6}" for q in questions) + "answered@5")
    for name, _ in builders:
        row = [hits[(name, q["id"])] for q in questions]
        print(f"{name:<17}" + "".join(f"{str(x):<6}" for x in row) + f"{sum(x != '-' for x in row)}/5")


if __name__ == "__main__":
    main()
