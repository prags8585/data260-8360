#!/usr/bin/env python3
"""HW10 Part 4.3 follow-up: why is the Writer the dominant stage? The Writer's prompt is the question, the plan and the WHOLE catalogue facts JSON.
Ollama has to read (prefill) that prompt again for every new question, because the question comes first and so the shared catalogue text is never a common prefix.
This probe sends the Writer's real prompts to Ollama directly (same model and options) for distinct, never-seen questions in two orders and prints Ollama's own timings.
It does not change the production Writer."""
import json
import os
import sys
import time

os.environ.setdefault("CATALOGUE_SOURCE", "mysql")

from ollama import Client  # noqa: E402

from kafka_svc.brains import DEFAULT_PLAN, WRITER_SYSTEM  # noqa: E402
from kafka_svc.catalogue import gather_facts  # noqa: E402

# two disjoint sets of questions that were never sent to the Writer before, so Ollama's prompt cache cannot have seen them
SET_TODAY = ["Please tell me the department of DATA-260.", "Who is the instructor for CS-146 this term?", "How many seats does ENGR-200 have left?",
             "Is there room in DATA-230?", "What is DATA-245 called?", "Which courses are taught by Dr. Samuel Okafor?"]
SET_FACTS_FIRST = ["Tell me the department that runs CS-157A.", "Who is assigned to teach DATA-260?", "How many places remain in CS-146?",
                   "Does DATA-245 have free seats?", "What is the name of ENGR-200?", "Which courses does Dr. Priya Nair teach?"]
OPTIONS = {"temperature": 0.0, "seed": 8360, "num_predict": 400}


def run(client, label, make_prompt, questions):
    rows = []
    for q in questions:
        t = time.perf_counter()
        r = client.chat(model="qwen3:8b", messages=[{"role": "system", "content": WRITER_SYSTEM}, {"role": "user", "content": make_prompt(q)}], think=False, options=OPTIONS)
        rows.append({"wall_ms": (time.perf_counter() - t) * 1000, "prompt_tokens": r["prompt_eval_count"], "prefill_ms": r["prompt_eval_duration"] / 1e6,
                     "generate_ms": r["eval_duration"] / 1e6, "output_tokens": r["eval_count"]})
    mean = lambda k: sum(x[k] for x in rows) / len(rows)  # noqa: E731
    print(f"{label:34} wall {mean('wall_ms'):7.0f} ms   prefill {mean('prefill_ms'):7.0f} ms ({mean('prompt_tokens'):.0f} tokens read)   generate {mean('generate_ms'):6.0f} ms ({mean('output_tokens'):.0f} tokens)")
    return rows


def main() -> int:
    client = Client()
    facts = json.dumps(gather_facts("q"))
    client.chat(model="qwen3:8b", messages=[{"role": "user", "content": "hi"}], think=False, options={"num_predict": 2})  # model is loaded
    original = lambda q: f"Question: {q}\nPlan: {json.dumps(DEFAULT_PLAN)}\nFacts: {facts}"  # noqa: E731  (what writer.py sends today)
    facts_first = lambda q: f"Facts: {facts}\nPlan: {json.dumps(DEFAULT_PLAN)}\nQuestion: {q}"  # noqa: E731
    a = run(client, "Writer prompt as sent today", original, SET_TODAY)
    b = run(client, "facts first (shared prefix)", facts_first, SET_FACTS_FIRST)
    print(f"-> Ollama prefill is {sum(x['prefill_ms'] for x in a) / sum(x['wall_ms'] for x in a):.0%} of the Writer's wall time today; with the facts first it is "
          f"{sum(x['prefill_ms'] for x in b) / sum(x['wall_ms'] for x in b):.0%}.")
    json.dump({"as_sent_today": a, "facts_first": b}, open("reports/hw10/raw/writer_prefill_probe.json", "w"), indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
