# METRICS.md — DATA-260 Homework 3, Part 2

Corpus: `corpus/hw03/` (16 real SJSU pages, 207,022 bytes; see `SOURCES.md` /
`CORPUS_MANIFEST.json`). Embedding model: `sentence-transformers/all-MiniLM-L6-v2`
(384-dim), local, HuggingFace. Vector store: LlamaIndex `SimpleVectorStore`
(in-memory). Evaluated against the 5 questions in `questions.yaml`, `k=5`.
Full per-query/per-technique output: `reports/hw03/raw/retrieval_records.json`
(and `.csv`). Console log with timestamps: `reports/hw03/RUN_LOG.txt`. Script:
`rag_chunking_comparison.py`.

## Retrieval Quality

| Technique | Chunks | Avg chunk length | Top-1 cosine | Mean@k cosine | Recall@k | Mean retrieval latency (ms) |
|---|---|---|---|---|---|---|
| Token | 204 | 1158.2 chars | 0.6968 | 0.6412 | 0.800 | 7.91 |
| Semantic | 85 | 2434.5 chars | 0.6523 | 0.6011 | 0.800 | 5.25 |
| Sentence window | 1307 | 158.3 chars | 0.7483 | 0.6883 | 0.800 | 15.83 |

Chunker settings: Token `chunk_size=256, chunk_overlap=32` (tokens); Semantic
`buffer_size=1, breakpoint_percentile_threshold=95` (LlamaIndex default); Sentence
window `window_size=3`.

## A confidently scored retrieval that does not contain the answer

**q3** ("What are the two specialization tracks in SJSU's MS in Applied Data
Intelligence program...") is the clearest case. Under **sentence-window**
chunking, the *highest-scoring* retrieved chunk of the whole run
(`store_score=0.7244`) is:

> "Entertainment Waymo World Bank Learn more about what alumni from SJSU's MS
> in Applied Data Intelligence - formerly the MS in Data Analytics - have
> accomplished."

— a fragment of an alumni-outcomes employer list from `msda_curriculum_courses.txt`.
It contains no mention of "Analytics Technologies," "Data Engineering," or any
elective course. The actual answer (`applied_data_intelligence_ms_program.txt`,
listing both specializations and their DATA 225/226/236/240/265/266 electives)
only shows up at **rank 5**, scoring *lower* (`0.6903`) than this wrong hit.

**Why the embedding likely considered it similar:** the query and this chunk
share the exact phrase "MS in Applied Data Intelligence" verbatim, and sentence-
window chunking embeds each node as a single ~150-character sentence in
isolation, with no surrounding paragraph to signal "this is an alumni-employer
list, not a program-requirements section." With that little context, a small
bi-encoder like MiniLM leans heavily on the lexical/topical overlap of the
program name itself, so a sentence that is *about the program in name only*
scores about as high as a sentence that actually answers the question. Coarser
chunking (Token, Semantic) doesn't show this failure mode for q3 — their larger
chunks dilute the "program name" signal with enough surrounding real content
that the correct program-requirements chunk still ranks in the top 3.

