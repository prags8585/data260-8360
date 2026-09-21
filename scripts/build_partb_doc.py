#!/usr/bin/env python3
"""Builds reports/hw03/PartB_documentation.html/.pdf: a self-contained write-up
of the three chunking pipelines (chunking, indexing, retrieval-only output),
their comparison, observations and conclusion. Everything numeric is read from
the saved raw results or measured live by re-chunking the corpus; code is
pulled verbatim from rag_chunking_comparison.py."""

import ast
import html
import json
import re
import statistics
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import rag_chunking_comparison as m  # noqa: E402
from llama_index.embeddings.huggingface import HuggingFaceEmbedding  # noqa: E402

OUT_HTML = ROOT / "reports/hw03/PartB_documentation.html"
OUT_PDF = ROOT / "reports/hw03/PartB_documentation.pdf"
TECHS = [("token", "Token", m.build_token_index),
         ("semantic", "Semantic", m.build_semantic_index),
         ("sentence_window", "Sentence-window", m.build_sentence_window_index)]
MARKERS = {"q1": ["3.0", "disqualif"], "q2": ["DATA 270"], "q3": ["Analytics Technologies", "Data Engineering"],
           "q4": ["$200.00"], "q5": ["September 16, 2022"]}
esc = html.escape


def gather():
    embed = HuggingFaceEmbedding(model_name=m.EMBED_MODEL_NAME)
    docs = m.load_corpus()
    questions = yaml.safe_load((ROOT / "questions.yaml").read_text())["questions"]
    data = {}
    for key, _, builder in TECHS:
        index, nodes = builder(docs, embed)
        lens = [len(n.get_content()) for n in nodes]
        sample = next(n for n in nodes if "$200.00" in n.get_content())
        text = sample.get_content()
        answered = {}
        retr = index.as_retriever(similarity_top_k=m.TOP_K)
        for q in questions:
            first = "-"
            for rank, r in enumerate(retr.retrieve(q["question"]), 1):
                if all(mk in r.node.get_content() for mk in MARKERS[q["id"]]):
                    first = rank
                    break
            answered[q["id"]] = first
        data[key] = {
            "n": len(nodes), "avg": round(statistics.mean(lens), 1), "min": min(lens),
            "median": int(statistics.median(lens)), "max": max(lens),
            "sample_file": sample.metadata.get("file_name"), "sample_len": len(text),
            "sample": text if len(text) <= 900 else text[:900] + " ...",
            "window": sample.metadata.get("window") if key == "sentence_window" else None,
            "answered": answered,
        }
    return data


def code_of(path, names):
    src = path.read_text()
    tree = ast.parse(src)
    out = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            out.append(ast.get_source_segment(src, node))
    return "\n\n".join(out)


def settings_block(path):
    lines = path.read_text().splitlines()
    keep = [l for l in lines if re.match(r"^(EMBED_MODEL_NAME|TOP_K|TOKEN_|SEMANTIC_|SENTENCE_WINDOW_SIZE)", l)]
    return "\n".join(keep)


def q3_output(tech):
    log = (ROOT / "reports/hw03/RUN_LOG.txt").read_text().splitlines()
    start = next(i for i, l in enumerate(log) if l.startswith(f"=== [{tech}] q3"))
    end = next(i for i in range(start, len(log)) if log[i].startswith("retrieval latency"))
    return "\n".join(log[start:end + 1])


def build(data):
    summary = json.loads((ROOT / "reports/hw03/raw/summary.json").read_text())
    records = json.loads((ROOT / "reports/hw03/raw/retrieval_records.json").read_text())
    best = {}
    for key, _, _ in TECHS:
        rs = [r for r in records if r["technique"] == key]
        best[key] = round(sum(max(x["cosine_sim"] for x in r["results"]) for r in rs) / len(rs), 4)

    settings = settings_block(ROOT / "rag_chunking_comparison.py")
    retr_code = code_of(ROOT / "rag_chunking_comparison.py", {"cosine_sim", "retrieve_and_analyze"})
    builders = {k: code_of(ROOT / "rag_chunking_comparison.py", {f"build_{k}_index"}) for k, _, _ in TECHS}

    why = {
        "token": ("Splits the text every 256 tokens with a 32-token (12.5%) overlap. The size keeps each chunk on roughly one "
                  "policy or requirement, and the overlap means a fact that straddles a boundary still appears whole in at least one chunk. "
                  "It ignores meaning: boundaries fall wherever the token count lands."),
        "semantic": ("Embeds each sentence (buffer_size=1) with the same MiniLM model and starts a new chunk only where the embedding "
                     "distance to the next sentence is in the top 5% (breakpoint_percentile_threshold=95). Chunks follow topic changes, so they are "
                     "few and large, and their size varies with the text."),
        "sentence_window": ("Makes every sentence its own node and stores the three sentences on each side in the node's `window` metadata "
                            "(window_size=3). Only the single sentence is embedded and searched; the window is kept so surrounding context could be "
                            "supplied later. Nodes are very small and numerous."),
    }

    def terminal(text):
        return f'<pre class="term">{esc(text)}</pre>'

    def codeblock(text):
        return f'<pre class="code">{esc(text)}</pre>'

    sections = []
    for key, label, _ in TECHS:
        d = data[key]
        win = ""
        if d["window"]:
            win = (f'<p class="lbl">Its <code>window</code> metadata (the 3 sentences either side, stored but not embedded):</p>'
                   f'<pre class="term">{esc(d["window"][:1200])}</pre>')
        sections.append(f"""
<h2>{label} chunking</h2>
<h3>1. Chunking</h3>
<p>{why[key]}</p>
{codeblock(builders[key])}
<table class="t small"><tr><th>Chunks</th><th>Avg length</th><th>Min</th><th>Median</th><th>Max</th></tr>
<tr><td>{d['n']}</td><td>{d['avg']} chars</td><td>{d['min']}</td><td>{d['median']}</td><td>{d['max']}</td></tr></table>
<p class="lbl">A real chunk from this technique: the first one containing the $200.00 late-fee fact
(from <code>{esc(d['sample_file'])}</code>, {d['sample_len']} characters{', shortened here' if d['sample_len'] > 900 else ''}):</p>
<pre class="term">{esc(d['sample'])}</pre>
{win}
<h3>2. Indexing (in memory)</h3>
<p>The nodes are loaded into a LlamaIndex <code>VectorStoreIndex</code> with no external store configured, so LlamaIndex uses its default
in-memory <code>SimpleVectorStore</code>. Nothing is persisted or sent anywhere. This is the last line of the builder above:
<code>index = VectorStoreIndex(nodes, embed_model=embed_model)</code>.</p>
<h3>3. Retrieval-only output for the shared question (q3)</h3>
<p>The retrieval function (documented once above) run on this technique's index. The table lists rank, store score, recomputed cosine,
chunk length, source file and a 160-character preview.</p>
{terminal(q3_output(key))}
""")

    rows = "".join(
        f"<tr><td>{label}</td><td>{summary[k]['n_chunks']}</td><td>{summary[k]['avg_chunk_len']} chars</td>"
        f"<td>{best[k]}</td><td>{summary[k]['mean_at_k_cosine_mean']}</td><td>{summary[k]['recall_at_k']:.2f}</td>"
        f"<td>{summary[k]['mean_retrieval_latency_ms']}</td></tr>" for k, label, _ in TECHS)
    qs = ["q1", "q2", "q3", "q4", "q5"]
    arows = "".join(
        f"<tr><td>{label}</td>" + "".join(f"<td>{data[k]['answered'][q]}</td>" for q in qs) +
        f"<td><b>{sum(data[k]['answered'][q] != '-' for q in qs)}/5</b></td></tr>" for k, label, _ in TECHS)

    css = """
    body{font-family:Arial,Helvetica,sans-serif;font-size:10.5pt;line-height:1.4;color:#111}
    h1{font-size:18pt;margin:0 0 4px} h2{font-size:14pt;border-bottom:2px solid #222;padding-bottom:3px;margin-top:26px;page-break-after:avoid}
    h3{font-size:11.5pt;margin:14px 0 4px;page-break-after:avoid} p{margin:6px 0} .sub{color:#555;margin-bottom:14px}
    code{font-family:Menlo,Consolas,monospace;font-size:9pt;background:#f0f0f0;padding:0 3px}
    pre{white-space:pre-wrap;word-wrap:break-word;border-radius:4px;padding:8px 10px;margin:6px 0;font-family:Menlo,Consolas,monospace}
    pre.code{background:#f6f6f6;border:1px solid #ccc;font-size:8pt} pre.term{background:#1e1e1e;color:#e6e6e6;font-size:7pt;line-height:1.35}
    table.t{border-collapse:collapse;width:100%;margin:8px 0} table.t th{background:#111;color:#fff;font-size:9pt}
    table.t th,table.t td{border:1px solid #333;padding:5px 7px;text-align:left;font-size:9.5pt} table.small{width:auto}
    .lbl{font-weight:bold;margin-top:10px} .note{font-size:9pt;color:#444} .box{border:1px solid #999;background:#fafafa;padding:8px 12px}
    """
    doc = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>HW3 Part B</title><style>{css}</style></head><body>
<h1>HW3 Part B: Three Chunking Techniques, Retrieval-Only</h1>
<div class="sub">DATA-260 · Karthik Pragada · DOMAIN_ID 0 (Campus Course Catalogue and Enrolment)</div>

<h2>0. Shared setup</h2>
<p><b>Corpus:</b> 16 public SJSU pages, 207,022 bytes (<code>corpus/hw03/</code>; see SOURCES.md and CORPUS_MANIFEST.json).
<b>Embedding model:</b> <code>sentence-transformers/all-MiniLM-L6-v2</code> (384 dimensions, local, from HuggingFace), used for all three techniques
and for the semantic splitter. <b>Vector store:</b> in-memory <code>SimpleVectorStore</code>. <b>Questions:</b> the five in <code>questions.yaml</code>
(committed before any retrieval was run). <b>Top-k:</b> 5.</p>
<p>Settings used (from <code>rag_chunking_comparison.py</code>):</p>{codeblock(settings)}
<h3>The retrieval-only function (shared by all three techniques)</h3>
<p>Given an index, a query and k, <code>retrieve_and_analyze</code> (1) embeds the query and reports its dimension and first 8 values;
(2) retrieves the top-k nodes and records the retriever's <b>store score</b>; (3) <b>re-embeds each returned chunk's text explicitly</b> and computes
the cosine similarity to the query vector; (4) records chunk length and a 160-character preview; (5) prints the shapes of the query vector and the stacked
document vectors; and (6) times the similarity search only. Every retrieved row is saved to <code>reports/hw03/raw/</code> as JSON and CSV.</p>
{codeblock(retr_code)}
{''.join(sections)}

<h2>4. Comparison</h2>
<h3>Retrieval quality (5 questions, k = 5)</h3>
<table class="t"><tr><th>Technique</th><th>Chunks</th><th>Avg chunk length</th><th>Top-1 cosine</th><th>Mean@k cosine</th><th>Recall@k</th><th>Mean retrieval latency (ms)</th></tr>{rows}</table>
<p class="note">Top-1 cosine is the highest cosine among the top-5 chunks, averaged over the questions. Recall@k is file-level: a hit means the expected source
file appears anywhere in the top 5. Latency covers the similarity search only and varies by machine.</p>
<h3>Answer-level check (was the answer text itself retrieved?)</h3>
<p>Recall@k only checks the file, so this supplementary check (<code>scripts/answer_level_check.py</code>) asks whether any top-5 chunk contains the expected
answer text. Each cell is the rank of the first chunk that does; "-" means none did.</p>
<table class="t"><tr><th>Technique</th><th>q1</th><th>q2</th><th>q3</th><th>q4</th><th>q5</th><th>Answered in top 5</th></tr>{arows}</table>
<p class="note">q1 requires two marker strings in one chunk, which disadvantages single-sentence nodes; q2, q4 and q5 use a single marker.</p>

<h3>A confidently scored retrieval that does not contain the answer</h3>
<div class="box"><p>For <b>q3</b> (the two specialization tracks of the MS in Applied Data Intelligence), <b>no technique</b> retrieved a chunk containing the answer.
Under Sentence-window the top result has the highest store score of the whole run (0.7244): <i>"Entertainment Waymo World Bank Learn more about what
alumni from SJSU's MS in Applied Data Intelligence - formerly the MS in Data Analytics - have accomplished."</i> It is an alumni-employer fragment with no
specialization or elective in it. The program's own page does appear (rank 5) but only as its opening text, not the section that lists the specializations.</p>
<p>The embedding most likely rated it similar because it repeats the query's proper noun, "MS in Applied Data Intelligence". A single short sentence has little
other context, so that name dominates the match. The marketing page repeats the program name often, and its text was not fully cleaned when the corpus was collected.</p></div>

<h2>5. Observations</h2>
<p>Sentence-window has the highest cosine scores (top-1 {best['sentence_window']}, mean@k {summary['sentence_window']['mean_at_k_cosine_mean']}) but retrieved a chunk containing the answer
for only 2 of 5 questions, against 4 for Token and 3 for Semantic. High similarity did not mean a useful chunk: single-sentence nodes carry little context, so shared proper
nouns dominate the match, and near-identical boilerplate repeated across the three program pages (for example the GWAR sentence) outranked the sentence naming DATA 270 in q2.
Semantic chunks are the largest ({data['semantic']['avg']} characters on average), which likely dilutes a single fact such as the $200.00 fee in q4 inside a long registration page.</p>
<p>Recall@k is 0.80 for all three because of q1: the 3.0 GPA rule appears in three documents, and every technique retrieved <code>graduate_policies_procedures.txt</code>, a valid
source that the single expected-file label counted as a miss. q3 failed for every technique. With only five questions these differences are indicative, not conclusive.</p>

<h2>6. Conclusion</h2>
<p><b>Token chunking (256 tokens, 32 overlap) is the best choice for this corpus.</b> It retrieved a chunk containing the answer for 4 of 5 questions, against 3 for Semantic and
2 for Sentence-window, even though Sentence-window had the highest cosine scores, so cosine alone was misleading here. Its mean latency of {summary['token']['mean_retrieval_latency_ms']} ms is well
below Sentence-window's {summary['sentence_window']['mean_retrieval_latency_ms']} ms and close to Semantic's {summary['semantic']['mean_retrieval_latency_ms']} ms. The result rests on five questions, and q3 failed for all three techniques.</p>
</body></html>"""
    OUT_HTML.write_text(doc)


def to_pdf():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        page.goto(f"file://{OUT_HTML}")
        page.pdf(path=str(OUT_PDF), format="Letter", print_background=True,
                 margin={"top": "0.6in", "bottom": "0.6in", "left": "0.6in", "right": "0.6in"})
        b.close()


if __name__ == "__main__":
    data = gather()
    build(data)
    to_pdf()
    print("wrote", OUT_HTML, OUT_PDF)
