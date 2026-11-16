#!/usr/bin/env python3
"""Prints the spans of one trace_id in stage order (the command-line version of the dashboard's trace lookup)."""
import sys

from tracing.spans import trace_file
from tracing.store import by_trace, load_spans, trace_summary


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python scripts/hw10_show_trace.py <trace_id> [spans.jsonl]")
        return 2
    spans = by_trace(load_spans(sys.argv[2] if len(sys.argv) > 2 else trace_file())).get(sys.argv[1])
    if not spans:
        print(f"no spans for trace_id {sys.argv[1]}")
        return 1
    summary = trace_summary(spans)
    print(f"trace_id {summary['trace_id']}   path: {summary['path']}   total {summary['total_ms']} ms" + (f"   FAILED at {summary['failing_stage']}: {summary['error']}" if summary["failing_stage"] else ""))
    print(f"{'stage':18} {'start (UTC)':26} {'end (UTC)':26} {'ms':>9}  status  error")
    for s in spans:
        print(f"{s['stage']:18} {s['start']:26} {s['end']:26} {s['duration_ms']:>9.1f}  {s['status']:6}  {(s['error'] or '')[:62] + ('...' if len(s['error'] or '') > 62 else '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
