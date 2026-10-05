# AI_USE.md — DATA-260 Homework 5

## 1. What did you use an AI assistant for, and what did you do yourself?

I told Claude Code to extend the existing HW4 project (not start a new one), to leave everything unpushed until I had checked it, and to produce a report in the
same format as my HW4 report with realistic VS Code-style code images and real output. The domain (Course Catalogue), the FastAPI + MySQL service and the local Ollama model (`qwen3:8b`) all
carry over from earlier homeworks.

Claude Code wrote and ran the implementation: the `instructors` table and migration, the Pydantic-validated catalog API, the Redux Toolkit client, both
MCP servers, the retry/timeout module, the fault-injection experiment, `execute_tool`, the safety rule, the agent loop, the offline tests,
`verify_hw05.py`, and the report generator. It drove the real MCP Inspector and a real browser for the screenshots. I am responsible for reviewing the code,
the numbers and the report before pushing and submitting.

## 2. One AI-produced output that was wrong/unsuitable, or one thing you independently verified

The plan assumed the MCP Python SDK's `FastMCP` class, as the assignment describes. A plain `pip install "mcp[cli]"` now installs MCP 2.x, where `FastMCP` was
renamed, so the first import of `mcp.server.fastmcp` failed and the servers as planned could not run.

## 3. How you detected the problem or verified the result

The import error was caught immediately by running the import before writing the servers; the SDK's own message named the rename and pointed to pinning `mcp<2`.
I also checked that nothing else relied on 2.x APIs by running both servers over real STDIO and through the actual MCP Inspector (`mcp dev`), not just importing them.

## 4. What you changed and why it works now

The environment pins `mcp[cli]<2` (v1.30.0), which matches the `FastMCP` API the assignment is written around. Both servers now start, list the correct tools
(4 and 3), and answer valid and invalid calls over STDIO; `verify_hw05.py` repeats that check. A second thing worth recording: my first fault-injection run showed a
139 ms p99 at 0% failures, which was not a retry effect but the first database connection warming up. I added one uncounted warm-up query and re-ran, and the
0% p99 dropped to 11 ms.
