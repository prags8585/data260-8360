#!/usr/bin/env python3
"""Drives both MCP servers over real STDIO JSON-RPC (the same protocol the
MCP Inspector speaks) and saves every call's input and output to
reports/hw05/raw/mcp_inspector/. Also lists each server's tool schemas.

Usage: python scripts/mcp_probe.py
"""

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports/hw05/raw/mcp_inspector"
OUT.mkdir(parents=True, exist_ok=True)

MEALS_CALLS = [
    ("search_meals_by_name", {"query": "Arrabiata", "limit": 3}, "valid"),
    ("search_meals_by_name", {"query": "zzzxxyy", "limit": 5}, "no results"),
    ("search_meals_by_name", {"query": "Arrabiata", "limit": 99}, "invalid: limit out of range"),
    ("meals_by_ingredient", {"ingredient": "chicken", "limit": 5}, "valid"),
    ("random_meal", {}, "valid"),
    ("meal_details", {"id": 52771}, "valid"),
    ("meal_details", {"id": 0}, "no results"),
]

DOMAIN_CALLS = [
    ("search_courses", {"query": "database", "limit": 5}, "valid"),
    ("search_courses", {"query": "", "limit": 5}, "invalid: empty query"),
    ("course_detail", {"course_id": 1}, "valid"),
    ("course_detail", {"course_id": -3}, "invalid: not a positive integer"),
    ("course_detail", {"course_id": 9999}, "invalid: unknown id"),
    ("course_stats", {"group_by": "department"}, "valid"),
    ("course_stats", {"group_by": "instructor"}, "valid"),
    ("course_stats", {"group_by": "color"}, "invalid: unsupported group_by"),
]


async def probe(server_file: str, calls: list, label: str) -> dict:
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / server_file)], cwd=str(ROOT))
    record = {"server_file": server_file, "tools": [], "calls": []}
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            record["server_name"] = init.serverInfo.name
            for t in (await session.list_tools()).tools:
                record["tools"].append({"name": t.name, "description": t.description, "inputSchema": t.inputSchema})
            for tool, args, note in calls:
                res = await session.call_tool(tool, args)
                blocks = []
                for c in res.content:
                    if getattr(c, "type", "") != "text":
                        continue
                    try:
                        blocks.append(json.loads(c.text))
                    except ValueError:
                        blocks.append(c.text)
                text = " ".join(json.dumps(b) if not isinstance(b, str) else b for b in blocks)
                parsed = blocks[0] if len(blocks) == 1 else blocks
                record["calls"].append({"tool": tool, "input": args, "note": note, "isError": bool(res.isError), "output": parsed})
                short = text[:110]
                print(f"  [{label}] {tool}({json.dumps(args)}) isError={bool(res.isError)} -> {short}")
    return record


async def main():
    print("== meals server (TheMealDB) ==")
    meals = await probe("meals_server.py", MEALS_CALLS, "meals")
    (OUT / "meals_server_calls.json").write_text(json.dumps(meals, indent=2))
    print("== domain server (s8360_rel) ==")
    domain = await probe("domain_server.py", DOMAIN_CALLS, "campus")
    (OUT / "domain_server_calls.json").write_text(json.dumps(domain, indent=2))
    print(f"tools -> meals: {[t['name'] for t in meals['tools']]}  campus: {[t['name'] for t in domain['tools']]}")
    print(f"saved to {OUT}")


asyncio.run(main())
