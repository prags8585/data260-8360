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

## Observations

Sentence-window chunking has the highest top-1 and mean@k cosine on average
(0.7483 / 0.6883) *and* the case above showing its most dangerous failure mode:
because each node is a single short, decontextualized sentence, a chunk can
score confidently high purely on lexical overlap with the query's proper nouns
while containing none of the actual substance — the semantic-similarity score
and "is this chunk useful" are least correlated for this technique specifically
because there's so little content per chunk to disambiguate on. Token and
Semantic chunking produce fewer, larger chunks (204 and 85 respectively, versus
1307) that carry enough surrounding context to make a lexical-overlap-only
match less likely to outrank a substantively relevant one — visible in q3's
Token and Semantic results, where the correct program page lands at rank 2-3
instead of rank 5.

Semantic chunking has the *lowest* average scores of the three (fewest chunks,
largest average chunk size at 2434 chars) — merging multiple loosely-related
sentences into each chunk dilutes the embedding toward a "topic centroid" that
matches any one specific query less precisely, which also explains its lowest
mean retrieval latency (5.25 ms): only 85 vectors to search.

All three techniques tied on Recall@5 (0.800 = 4/5 questions). The one miss in
all three is **q1**, whose `questions.yaml` entry is explicitly flagged
`single_source: false` — the 3.0-GPA-probation fact genuinely appears in three
different documents (`grades_policy.txt`, `graduate_policies_procedures.txt`,
`undergraduate_policies_procedures.txt`). All three techniques consistently
retrieved `graduate_policies_procedures.txt` and `undergraduate_policies_procedures.txt`
instead of the single `expected_source_file` I'd picked — which is a limitation
of scoring Recall@k against one hand-picked "correct" document for a fact that
legitimately isn't single-sourced, not a retrieval failure. The other four
(single-source) questions were recalled correctly by every technique.

## Conclusion

For this corpus, **Token chunking (chunk_size=256, overlap=32) is the best
overall choice for deployment.** It lands in between Semantic and
Sentence-window on retrieval quality (top-1 cosine 0.6968, mean@k 0.6412) but
without Sentence-window's demonstrated failure mode: at 1158 characters,
Token's chunks are large enough to carry real surrounding context (so a match
on a proper noun alone rarely outranks a substantively relevant chunk, as seen
in q3), while staying far more granular than Semantic's 2434-character chunks,
which lose precision on point-fact queries. Token chunking is also cheap
(204 chunks, 7.91 ms mean latency, well under Sentence-window's 15.83 ms from
having to search 1307 vectors) and its chunk_size is a single, well-understood
parameter to tune, unlike Semantic's breakpoint-percentile heuristic. Sentence-
window would only be worth its latency and reliability cost for a use case that
specifically needs the `window` metadata for downstream generation context,
which this retrieval-only comparison doesn't exercise.
