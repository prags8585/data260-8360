# AI_USE.md — DATA-260 Homework 6

## 1. What did you use an AI assistant for, and what did you do yourself?

I extended my existing HW5 project for this homework instead of creating a new project. I decided to continue using the same domain, FastAPI service, and local Ollama model (`qwen3:8b`) from the previous homeworks. I designed the required features, including the MongoDB document API, memory service, endpoints, conversation probes, experiment scripts, file-memory commands, and verification process.

I used Claude Code to help write and run few parts of the implementation, tests, experiment scripts, `verify_hw06.py`, and the report generator.  I was also responsible for checking the code, validating the outputs and numbers, testing the memory-consolidation behavior, reviewing the report, and deciding what was ready to submit.

## 2. One AI-produced output that was wrong/unsuitable, or one thing I independently verified

The first version of `file_memory.consolidate()` was not idempotent. It merged duplicate facts and resolved contradictions correctly on the 55-line memory file, but the “Resolved contradictions” audit section was treated as regular memory text during the next pass. As a result, running `/compact` a second time changed the file again instead of returning the same consolidated result.

The first version of my 55-line `MEMORY.md` also consolidated to 46 lines instead of meeting the requirement of fewer than 40 lines.

## 3. How did you detect the problem or verify the result?

I detected the idempotency problem by running the consolidation function a second time on its own output and comparing the result with the first pass. The second pass produced a different file, which showed that the function was not preserving an already-consolidated memory file.

I also found the line-count problem by running the consolidation test against my original fixture. Instead of weakening the requirement, I reviewed and rebalanced the fixture to contain 27 distinct topics and 14 duplicate lines so that the final consolidated result would meet the required limit.

## 4. What did you change and why does it work now?

I changed `parse_facts()` so it tracks `##` sections and keeps audit lines separate from actual memory facts. I also updated `render()` so duplicate audit lines are removed. After these changes, running `/compact` a second time returns the same 39-line result instead of changing the file again.

The test `tests_hw6.py::test_consolidation_of_the_55_line_memory_file` verifies both the first consolidation result and the second-pass result.

I also independently reviewed the contradiction-resolution results. The “most recent wins” rule incorrectly resolved two of the five contradictions, involving `work_hours` and `database_port`, because the newer values were temporary or qualified. I kept these cases marked as `NEEDS REVIEW` instead of allowing the system to make an unsupported decision. I documented this limitation in the report.

During testing, I also noticed that the episodic extractor sometimes saved a user’s question, such as “User asked about favorite course,” as if it were a permanent fact. I identified this as noise rather than durable memory and documented it as another limitation while keeping the extraction prompt unchanged so the saved experiment data remains consistent with the repository code.

## 5. Used Claudd to push the files to my github repo easily.