#!/usr/bin/env python3


from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CON = ROOT / "reports/hw07/raw/console"
PARTS = [
    ("00_mysql_users_table.txt", "docker exec ... mysql (scripts/hw7_db_evidence.py)", "Part 1 - MySQL users table (roles, bcrypt hashes)"),
    ("01_jwt_auth_evidence.txt", "PYTHONPATH=. python scripts/hw7_auth_evidence.py", "Part 1 - JWT login, /auth/me and the role policy (curl against PORT_BASE 8260)"),
    ("04_lint_precommit.txt", "PYTHONPATH=. python scripts/hw7_lint_demo.py <scratch dir>", "Part 1 - Ruff + pre-commit: error before commit, hook blocks, fix, successful commit"),
    ("02_agent_demo.txt", "PYTHONPATH=. python scripts/hw7_agent_demo.py", "Part 2 - tasks A, B, C and the nonexistent-id error recovery"),
    ("03_reliability.txt", "PYTHONPATH=. python scripts/hw7_reliability.py", "Part 2 - 30 attempts: well-formed call rate before/after repair"),
    ("05_reflexion_compare.txt", "PYTHONPATH=. python scripts/hw7_reflexion_compare.py 10", "Part 3 - original loop vs Reflexion loop (30 runs each)"),
    ("06_verifier_probe.txt", "PYTHONPATH=. python scripts/hw7_verifier_probe.py 10", "Part 3 - verifier strictness probe (false rejections without the chain guard)"),
    ("07_part4_ui_acceptance.txt", "PYTHONPATH=. python scripts/hw7_bikeshare_ui_demo.py", "Part 4 - both acceptance scenarios through the UI"),
    ("08_attack_eval.txt", "PYTHONPATH=. python scripts/hw7_attack_eval.py procedure:1,minimal:2", "Part 5 - prompt-injection attacks, before/after the defenses"),
    ("11_safety_gate_before_fix.txt", "PYTHONPATH=. python scripts/hw7_safety_gate_test.py before_fix", "Part 6 - the 10-command gate test against the first implementation (one false allow)"),
    ("09_file_tools_demo.txt", "PYTHONPATH=. python scripts/hw7_file_tools_demo.py", "Part 6 - combined run: file tools, glob -> search -> read, and the 10-command gate test after the fix"),
    ("10_tests_and_verify.txt", "python tests_hw7.py && PYTHONPATH=. python verify_hw07.py", "Offline tests and the smoke test (writes reports/hw07/verification.json)"),
]


def main() -> None:
    out = ["# RUN_LOG.txt - DATA-260 Homework 7 (Karthik Pragada, SID4 8360, PORT_BASE 8260)",
           "# Real console output captured on a MacBook Air (Apple M4, 16 GB), MySQL 8.0 and MongoDB in Docker, Ollama qwen3:8b.",
           "# Each block was produced by the command shown above it; timestamps are in the block headers or log lines.", ""]
    for name, cmd, title in PARTS:
        f = CON / name
        if f.exists():
            out += ["=" * 100, f"## {title}", f"$ {cmd}", "=" * 100, f.read_text().rstrip("\n"), ""]
    (ROOT / "reports/hw07/RUN_LOG.txt").write_text("\n".join(out))
    print("RUN_LOG lines:", len(out))


if __name__ == "__main__":
    main()
