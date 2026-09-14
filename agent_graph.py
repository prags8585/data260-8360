#!/usr/bin/env python3
import argparse
import json
import time
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, ValidationError, field_validator

from agents_demo import DEFAULT_CONTENT, DEFAULT_TITLE, PLANNER_SYSTEM, extract_json
from src.model_client import ModelClient

REVIEWER_SYSTEM = """You are the Reviewer agent in a two-agent tagging pipeline.
You will receive the original title/content and a Planner's draft JSON containing
3 tags and a summary. Critically check whether the tags are specific and accurate
to the content (not vague or generic), and whether the summary is at most 25 words
and faithful to the content.
Respond with ONLY valid JSON, no other text, in this exact schema:
{"tags": ["tag1", "tag2", "tag3"], "summary": "...", "has_issues": true or false, "feedback": "one short sentence describing the issue, or an empty string if there are none"}
If the draft already meets the standards, set has_issues to false and return the
same tags/summary unchanged. If not, set has_issues to true, explain the issue in
feedback, and return improved tags/summary."""

TURN_CEILING_DEFAULT = 6


class TagsSummarySchema(BaseModel):

    tags: List[str]
    summary: str

    @field_validator("tags")
    @classmethod
    def check_tags(cls, v: List[str]) -> List[str]:
        if len(v) != 3:
            raise ValueError(f"must have exactly 3 tags, got {len(v)}")
        for tag in v:
            if not (3 <= len(tag) <= 30):
                raise ValueError(f"tag {tag!r} must be 3-30 characters long (got {len(tag)})")
        return v

    @field_validator("summary")
    @classmethod
    def check_summary(cls, v: str) -> str:
        word_count = len(v.split())
        if word_count > 25:
            raise ValueError(f"summary must be at most 25 words (got {word_count})")
        return v


class AgentState(TypedDict):
    title: str
    content: str
    email: str
    strict: bool
    task: str
    llm: Any
    planner_proposal: Optional[Dict[str, Any]]
    reviewer_feedback: Optional[Dict[str, Any]]
    schema_checked: bool
    turn_count: int
    planner_calls: int
    force_issue: bool


def planner_node(state: AgentState) -> Dict[str, Any]:
    print("--- NODE: Planner ---")
    llm: ModelClient = state["llm"]
    user_prompt = f"Title: {state['title']}\n\nContent: {state['content']}"

    feedback = state.get("reviewer_feedback")
    if feedback:
        user_prompt += (
            f"\n\nYour previous draft was: "
            f"{json.dumps({'tags': feedback.get('tags'), 'summary': feedback.get('summary')})}"
            f"\nThe reviewer found this issue: {feedback.get('feedback', '')}"
            f"\nProduce a revised draft that addresses this feedback."
        )

    messages = [("system", PLANNER_SYSTEM), ("human", user_prompt)]
    result = llm.complete(messages)
    proposal = extract_json(result.content)
    print(json.dumps(proposal, indent=2))

    # Reset reviewer_feedback / schema_checked so the router re-validates and
    # re-reviews this new proposal from scratch, instead of reusing stale state.
    return {
        "planner_proposal": proposal,
        "reviewer_feedback": None,
        "schema_checked": False,
        "planner_calls": state.get("planner_calls", 0) + 1,
    }


def validate_node(state: AgentState) -> Dict[str, Any]:
    """Part 4: deterministic Pydantic validation gate, no LLM call. On failure,
    synthesizes a reviewer_feedback-shaped rejection so the existing has_issues
    loop-back path sends it straight back to the Planner for a retry."""
    print("--- NODE: Validate (Pydantic) ---")
    proposal = state["planner_proposal"] or {}
    try:
        TagsSummarySchema(**proposal)
        print("valid")
        return {"schema_checked": True}
    except ValidationError as exc:
        error_msg = "; ".join(e["msg"] for e in exc.errors())
        print(f"INVALID: {error_msg}")
        return {
            "schema_checked": True,
            "reviewer_feedback": {
                "tags": proposal.get("tags", []),
                "summary": proposal.get("summary", ""),
                "has_issues": True,
                "feedback": f"Schema validation failed: {error_msg}",
            },
        }


def reviewer_node(state: AgentState) -> Dict[str, Any]:
    print("--- NODE: Reviewer ---")
    llm: ModelClient = state["llm"]
    user_prompt = (
        f"Title: {state['title']}\n\nContent: {state['content']}"
        f"\n\nPlanner draft:\n{json.dumps(state['planner_proposal'])}"
    )
    messages = [("system", REVIEWER_SYSTEM), ("human", user_prompt)]
    result = llm.complete(messages)
    feedback = extract_json(result.content)

    if state.get("force_issue"):
        # Testing hook (Step 6 of the assignment): force the correction loop
        # to fire regardless of what the model actually said, to prove the
        # graph really routes back to the Planner instead of just ending.
        feedback["has_issues"] = True
        feedback["feedback"] = "(forced for testing the correction loop)"

    print(json.dumps(feedback, indent=2))
    return {"reviewer_feedback": feedback}


def supervisor_node(state: AgentState) -> Dict[str, Any]:
    """State-updating only -- does not decide where to go next. That's
    router_logic()'s job, evaluated on the state this node produces."""
    return {"turn_count": state.get("turn_count", 0) + 1}


def router_logic(state: AgentState) -> str:
    if state.get("turn_count", 0) > TURN_CEILING_DEFAULT:
        print(f"--- ROUTER: turn ceiling ({TURN_CEILING_DEFAULT}) reached -- ending ---")
        return END
    if not state.get("planner_proposal"):
        print("--- ROUTER: no proposal yet -> planner ---")
        return "planner"
    if not state.get("schema_checked"):
        print("--- ROUTER: proposal not yet schema-validated -> validate ---")
        return "validate"
    feedback = state.get("reviewer_feedback")
    if feedback and feedback.get("has_issues"):
        print("--- ROUTER: issues found -> planner (self-correction) ---")
        return "planner"
    if not feedback:
        print("--- ROUTER: schema OK, not yet reviewed -> reviewer ---")
        return "reviewer"
    print("--- ROUTER: no issues -> END ---")
    return END


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("planner", planner_node)
    graph.add_node("validate", validate_node)
    graph.add_node("reviewer", reviewer_node)

    graph.set_entry_point("supervisor")
    graph.add_conditional_edges(
        "supervisor",
        router_logic,
        {"planner": "planner", "validate": "validate", "reviewer": "reviewer", END: END},
    )
    graph.add_edge("planner", "supervisor")
    graph.add_edge("validate", "supervisor")
    graph.add_edge("reviewer", "supervisor")

    return graph.compile()


def finalize(state: Dict[str, Any]) -> Dict[str, Any]:
    source = state.get("reviewer_feedback") or state.get("planner_proposal") or {}
    tags = list(source.get("tags", []))[:3]
    while len(tags) < 3:
        tags.append("general")
    summary = str(source.get("summary", "")).strip()
    words = summary.split()
    if len(words) > 25:
        summary = " ".join(words[:25])
    return {"tags": tags, "summary": summary}


def run(title, content, model, temperature, ceiling, force_issue, verbose=True):
    global TURN_CEILING_DEFAULT
    TURN_CEILING_DEFAULT = ceiling

    app = build_graph()
    initial_state: AgentState = {
        "title": title,
        "content": content,
        "email": "",
        "strict": True,
        "task": "tag_and_summarize",
        "llm": ModelClient(model=model, temperature=temperature),
        "planner_proposal": None,
        "reviewer_feedback": None,
        "schema_checked": False,
        "turn_count": 0,
        "planner_calls": 0,
        "force_issue": force_issue,
    }

    start = time.time()
    final_state = initial_state
    for step in app.stream(initial_state):
        for node_name, update in step.items():
            if verbose:
                print(f"=== after node: {node_name} ===")
            final_state = {**final_state, **update}
    elapsed_ms = (time.time() - start) * 1000

    abandoned = final_state.get("turn_count", 0) > ceiling
    retries = max(final_state.get("planner_calls", 1) - 1, 0)
    result = finalize(final_state)

    if verbose:
        print("\n" + "=" * 70)
        print("FINALIZED (Publish)")
        print("=" * 70)
        print(json.dumps(result, indent=2))
        print(f"\nTotal turns (supervisor visits): {final_state.get('turn_count')}")
        print(f"Planner calls: {final_state.get('planner_calls')} (retries: {retries})")
        print(f"Abandoned at ceiling: {abandoned}")
        print(f"Latency: {elapsed_ms:.0f} ms")

    return {
        "final_state": final_state,
        "result": result,
        "retries": retries,
        "abandoned": abandoned,
        "turn_count": final_state.get("turn_count", 0),
        "latency_ms": elapsed_ms,
    }


def main():
    parser = argparse.ArgumentParser(description="Stateful Planner/Reviewer agent graph (LangGraph) with schema validation.")
    parser.add_argument("--title", type=str, default=None)
    parser.add_argument("--content", type=str, default=None)
    parser.add_argument("--input", type=str, default=None, help="Path to JSON file with {title, content}")
    parser.add_argument("--model", type=str, default="qwen3:8b")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--ceiling", type=int, default=TURN_CEILING_DEFAULT, help="Max supervisor turns before forced stop")
    parser.add_argument("--force-issue", action="store_true", help="Force the Reviewer to always report an issue (tests the correction loop)")
    args = parser.parse_args()

    if args.input:
        with open(args.input) as f:
            data = json.load(f)
        title, content = data["title"], data["content"]
    elif args.title and args.content:
        title, content = args.title, args.content
    else:
        title, content = DEFAULT_TITLE, DEFAULT_CONTENT

    run(title, content, args.model, args.temperature, args.ceiling, args.force_issue)


if __name__ == "__main__":
    main()
