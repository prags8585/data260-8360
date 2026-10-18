# AGENT.md

Durable project and agent instructions. This file is loaded into the system prompt together with MEMORY.md.

## Project description
1. This repository is the DATA-260 Campus Course Catalogue service (domain entity: Course, DOMAIN_ID 0); it grows homework by homework in one codebase, never in a copy.
2. The service exposes a FastAPI backend on PORT_BASE 8260 with a React client in `frontend/`; per-homework evidence lives under `reports/hwNN/`.

## Technology stack
3. Python 3.12 with FastAPI, Pydantic v2, SQLAlchemy (MySQL `s8360_rel`) and PyMongo (MongoDB `s8360_doc`).
4. The local LLM is `qwen3:8b` served by Ollama, always reached through `src/model_client.py`.

## Coding conventions
5. Every function signature has type hints for all parameters and the return value.
6. Keep each function at 30 lines or fewer and give it one responsibility.
7. Use snake_case names; library modules log with `logging` and never call `print` (scripts under `scripts/` may print).

## Testing approach
8. Every new function gets an assert-based test in `tests_hw6.py` that runs offline: no network, no database, no LLM.

## Prohibited actions
9. Never write secrets, passwords or API keys into source files or logs.
10. Never overwrite or delete `MEMORY.md` without writing a backup copy first.
11. Never use `eval()` or `exec()`.

## Code review output format (from HW1)
When asked to review code, respond using **only a bullet-point list**.

Rules:
- Every line of your response must start with `-`.
- No introductory sentence, no summary paragraph, no closing remarks.
- No prose outside of bullets. No headings.
- Each bullet should state one specific issue or observation, concisely (one line each where possible).
- If the code has no issues, respond with a single bullet saying so -- do not pad with unnecessary bullets.
