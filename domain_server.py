#!/usr/bin/env python3
"""HW5 Part 2B: domain MCP server over the s8360_rel course catalogue.

Exactly three tools -- search, detail lookup, one aggregate -- all
answering with the same envelope {ok, data, error} (error is null on
success). Storage calls go through ResilientRepo (timeouts + bounded
exponential backoff, Part 3). STDIO rule: logs go to stderr, never stdout.

Run + debug:  mcp dev domain_server.py
"""

import domain_tools
from domain_tools import default_repo
from mcp.server.fastmcp import FastMCP

domain_tools.configure_logging()

mcp = FastMCP("campus")
repo = default_repo()


@mcp.tool()
def search_courses(query: str, limit: int = 10) -> dict:
    """Search the catalogue by course title, code or department (case-insensitive). limit is 1-50."""
    return domain_tools.search_courses(repo, query, limit)


@mcp.tool()
def course_detail(course_id: int) -> dict:
    """Full detail for one course by numeric id, including its instructor and seats available."""
    return domain_tools.course_detail(repo, course_id)


@mcp.tool()
def course_stats(group_by: str = "department") -> dict:
    """Aggregate: number of courses and total seats available, grouped by 'department' or 'instructor'."""
    return domain_tools.course_stats(repo, group_by)


if __name__ == "__main__":
    mcp.run(transport="stdio")
