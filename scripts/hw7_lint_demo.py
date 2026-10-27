#!/usr/bin/env python3

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BAD = '''import sys
import os
import json


def summarize(values):
    total = 0
    scaled = [v * 2 for v in values]
    return sum(values)


if __name__ == "__main__":
    print(summarize([1, 2, 3]))
'''
FIXED = '''def summarize(values):
    return sum(values)


if __name__ == "__main__":
    print(summarize([1, 2, 3]))
'''


def main() -> None:
    scratch = Path(sys.argv[1])
    work = scratch / "lintdemo" / "HW1_DATA260"
    if work.parent.exists():
        subprocess.run(["git", "worktree", "remove", "--force", str(work)], cwd=ROOT, capture_output=True)
        shutil.rmtree(work.parent, ignore_errors=True)
    work.parent.mkdir(parents=True)
    subprocess.run(["git", "branch", "-D", "hw7-lint-demo"], cwd=ROOT, capture_output=True)
    subprocess.run(["git", "worktree", "add", "-q", "-b", "hw7-lint-demo", str(work), "HEAD"], cwd=ROOT, check=True)
    for name in ("pyproject.toml", ".pre-commit-config.yaml"):
        shutil.copy(ROOT / name, work / name)
    (work / ".venv").symlink_to(ROOT / ".venv")
    env = {**os.environ, "PATH": f"{ROOT / '.venv/bin'}:{os.environ['PATH']}"}

    def run(command: str) -> int:
        print(f"$ {command}")
        done = subprocess.run(["bash", "-c", command], cwd=work, capture_output=True, text=True, env=env)
        print((done.stdout + done.stderr).rstrip())
        return done.returncode

    try:
        run("pre-commit install")
        (work / "lint_demo.py").write_text(BAD)
        print("\n# --- a file with lint problems is written (unused imports, unsorted imports, unused variables) ---")
        run("ruff check lint_demo.py")
        print("\n# --- commit attempt 1: the pre-commit hook runs and blocks the commit ---")
        run("git add lint_demo.py")
        run('git commit -m "HW7: add summarize helper"')
        print("\n# --- fix: Ruff removes the unused/unsorted imports, the unused variables are deleted by hand ---")
        run("ruff check --fix lint_demo.py")
        (work / "lint_demo.py").write_text(FIXED)
        run("ruff check lint_demo.py")
        print("\n# --- commit attempt 2: the hook passes and the commit is created ---")
        run("git add lint_demo.py")
        run('git commit -m "HW7: add summarize helper"')
        run("git log --oneline -2")
        (scratch / "lint_demo_bad.py").write_text(BAD)
        (scratch / "lint_demo_fixed.py").write_text(FIXED)
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(work)], cwd=ROOT, capture_output=True)
        subprocess.run(["git", "branch", "-D", "hw7-lint-demo"], cwd=ROOT, capture_output=True)


if __name__ == "__main__":
    main()
