#!/usr/bin/env python3
"""Planner -> Reviewer -> Finalizer agent pipeline over a local Ollama LLM."""

import argparse
import json
import re
import time

from langchain_ollama import ChatOllama

PLANNER_SYSTEM = """You are the Planner agent in a two-agent tagging pipeline.
Given a title and content, propose exactly 3 short topical tags (2-4 words each,
lowercase, specific to the content -- not generic categories) and a one-sentence
summary of at most 25 words that captures the key point of the content.
Respond with ONLY valid JSON, no other text, in this exact schema:
{"tags": ["tag1", "tag2", "tag3"], "summary": "..."}"""

REVIEWER_SYSTEM = """You are the Reviewer agent in a two-agent tagging pipeline.
You will receive the original title/content and a Planner's draft JSON containing
3 tags and a summary. Critically check whether the tags are specific and accurate
to the content (not vague or generic), and whether the summary is at most 25 words
and faithful to the content. If the draft already meets these standards, return it
unchanged. If not, return an improved version that does.
Respond with ONLY valid JSON, no other text, in this exact schema:
{"tags": ["tag1", "tag2", "tag3"], "summary": "..."}"""

DEFAULT_TITLE = "New Course: Distributed Systems Fundamentals"
DEFAULT_CONTENT = (
    "This course covers the design and implementation of distributed systems, "
    "including consensus algorithms, replication strategies, partitioning, and "
    "fault tolerance. Students will build a small key-value store that tolerates "
    "node failures and implement a leader election protocol. Prerequisites: "
    "data structures and computer networks."
)


def extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"Could not parse JSON from model output:\n{text}")


def call_agent(llm, system_prompt, user_prompt):
    messages = [("system", system_prompt), ("human", user_prompt)]
    start = time.time()
    response = llm.invoke(messages)
    elapsed_ms = (time.time() - start) * 1000
    parsed = extract_json(response.content)
    return parsed, elapsed_ms, response.content


def run_pipeline(title, content, model, temperature, verbose=True):
    llm = ChatOllama(model=model, temperature=temperature, format="json")
    user_prompt = f"Title: {title}\n\nContent: {content}"

    if verbose:
        print("=" * 70)
        print("PLANNER")
        print("=" * 70)
    planner_output, planner_ms, _ = call_agent(llm, PLANNER_SYSTEM, user_prompt)
    if verbose:
        print(json.dumps(planner_output, indent=2))
        print(f"(latency: {planner_ms:.0f} ms)\n")

    reviewer_prompt = f"{user_prompt}\n\nPlanner draft:\n{json.dumps(planner_output)}"

    if verbose:
        print("=" * 70)
        print("REVIEWER")
        print("=" * 70)
    reviewer_output, reviewer_ms, _ = call_agent(llm, REVIEWER_SYSTEM, reviewer_prompt)
    if verbose:
        print(json.dumps(reviewer_output, indent=2))
        print(f"(latency: {reviewer_ms:.0f} ms)\n")

    reviewer_changed = planner_output != reviewer_output

    # Finalization step -- deterministic, non-LLM: enforce the output contract.
    tags = list(reviewer_output.get("tags", []))[:3]
    while len(tags) < 3:
        tags.append("general")
    summary = str(reviewer_output.get("summary", "")).strip()
    words = summary.split()
    if len(words) > 25:
        summary = " ".join(words[:25])

    final_output = {"tags": tags, "summary": summary}

    if verbose:
        print("=" * 70)
        print("FINALIZED (Publish)")
        print("=" * 70)
        print(json.dumps(final_output, indent=2))

    return {
        "title": title,
        "model": model,
        "temperature": temperature,
        "planner": planner_output,
        "planner_latency_ms": planner_ms,
        "reviewer": reviewer_output,
        "reviewer_latency_ms": reviewer_ms,
        "reviewer_changed": reviewer_changed,
        "final": final_output,
        "total_latency_ms": planner_ms + reviewer_ms,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Planner -> Reviewer -> Finalizer agent demo over a local Ollama LLM."
    )
    parser.add_argument("--title", type=str, default=None)
    parser.add_argument("--content", type=str, default=None)
    parser.add_argument("--input", type=str, default=None, help="Path to JSON file with {title, content}")
    parser.add_argument("--model", type=str, default="qwen3:8b")
    parser.add_argument("--temperature", type=float, default=0.7)
    args = parser.parse_args()

    if args.input:
        with open(args.input) as f:
            data = json.load(f)
        title, content = data["title"], data["content"]
    elif args.title and args.content:
        title, content = args.title, args.content
    else:
        print("No --title/--content/--input given -- enter them now.")
        print(f"(press Enter on Title to use the default example: {DEFAULT_TITLE!r})\n")
        title = input("Title: ").strip()
        if not title:
            title, content = DEFAULT_TITLE, DEFAULT_CONTENT
        else:
            content = input("Content: ").strip()
        print()

    run_pipeline(title, content, args.model, args.temperature)


if __name__ == "__main__":
    main()
