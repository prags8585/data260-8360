

import difflib
import fnmatch
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

SANDBOX_ROOT = Path(tempfile.gettempdir()) / "course_sandbox"
MAX_BASH_OUTPUT = 4000

# --- safety gate ------------------------------------------------------------------------------

SAFE_PREFIXES = (
    "ls", "cat", "head", "tail", "wc", "pwd", "echo", "grep", "which", "date", "whoami", "sort", "uniq", "diff", "stat",
    "git status", "git diff", "git log", "python3 --version", "python --version",
)
_SEPARATORS = re.compile(r"\|\||&&|;|\||\n")
_ROOT_REDIRECT = re.compile(r">>?\s*(/(?!dev/null\b)\S*)")
_PRIVILEGE = {"sudo", "su", "doas", "pkexec"}
_PERMISSION = {"chmod", "chown", "chgrp", "setfacl", "chattr"}
_FS_CREATE = {"mkfs", "mke2fs", "mkswap", "wipefs"}


def _segments(command: str) -> list[str]:
    return [s.strip() for s in _SEPARATORS.split(command) if s.strip()]


def _tokens(segment: str) -> list[str] | None:
    try:
        return shlex.split(segment)
    except ValueError:  # unbalanced quotes: cannot be analysed, so treat as unsafe
        return None


def _is_recursive_rm(tokens: list[str]) -> bool:
    flags = [t for t in tokens[1:] if t.startswith("-")]
    return any(t == "--recursive" or (not t.startswith("--") and "r" in t.lower()) for t in flags)


def _writes_root_path_via_option(tokens: list[str]) -> bool:
    """Allow-listed commands can write files without a shell redirection: `sort -o FILE`, `git log --output=FILE`,
    `date -s` (sets the system clock) and `uniq INPUT OUTPUT`. Writing to an absolute path counts as a root-path write."""
    name = tokens[0].split("/")[-1]
    for i, tok in enumerate(tokens[1:], 1):
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if tok in ("-o", "--output") and nxt.startswith("/"):
            return True
        if tok.startswith("--output=/") or (tok.startswith("-o/") and len(tok) > 3):
            return True
    if name == "date" and any(t in ("-s", "--set") or t.startswith("--set=") for t in tokens[1:]):
        return True
    if name == "uniq":
        positional = [t for t in tokens[1:] if not t.startswith("-")]
        return len(positional) >= 2 and positional[1].startswith("/")
    return False


def _segment_destructive(segment: str) -> bool:
    tokens = _tokens(segment)
    if tokens is None:
        return True
    if _ROOT_REDIRECT.search(segment):
        return True
    if not tokens:
        return False
    name = tokens[0].split("/")[-1]
    if name in _PRIVILEGE or name in _PERMISSION:
        return True
    if name.startswith("mkfs") or name in _FS_CREATE:
        return True
    if name == "rm" and _is_recursive_rm(tokens):
        return True
    if name == "find" and ("-delete" in tokens or "-exec" in tokens):
        return True
    if name == "dd" and any(t.startswith("of=/dev/") for t in tokens):
        return True
    return _writes_root_path_via_option(tokens)


def is_destructive(command: str) -> bool:
    """True for recursive deletion, privilege escalation, permission/ownership changes, raw-device writes,
    filesystem creation or redirection to a root path in ANY part of a (possibly chained) command."""
    if "$(" in command or "`" in command:  # command substitution hides what will really run
        return True
    return any(_segment_destructive(seg) for seg in _segments(command))


def _matches_safe_prefix(segment: str) -> str | None:
    for prefix in SAFE_PREFIXES:
        if segment == prefix or segment.startswith(prefix + " "):
            return prefix
    return None


def confirm_bash(command: str, auto_approve: bool = False) -> dict:
    """Allow/block decision with a short reason. `auto_approve=True` means a human explicitly confirmed this command."""
    command = command.strip()
    if not command:
        return {"allowed": False, "reason": "empty command"}
    if is_destructive(command):
        if auto_approve:
            return {"allowed": True, "reason": "destructive command, allowed only because explicit confirmation was supplied"}
        return {"allowed": False, "reason": "destructive command: blocked, needs explicit confirmation"}
    prefixes = [_matches_safe_prefix(seg) for seg in _segments(command)]
    if prefixes and all(prefixes):
        return {"allowed": True, "reason": f"matches SAFE_PREFIXES ({', '.join(sorted(set(prefixes)))})"}
    if auto_approve:
        return {"allowed": True, "reason": "not on the allow-list, allowed because explicit confirmation was supplied"}
    return {"allowed": False, "reason": "not on the allow-list: needs confirmation"}


# --- file tools -------------------------------------------------------------------------------

def _root(root) -> Path:
    path = Path(root or SANDBOX_ROOT)
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _resolve(root: Path, path: str) -> Path | None:
    target = (root / path).resolve()
    return target if target == root or root in target.parents else None


def _err(message: str) -> dict:
    return {"ok": False, "error": message}


def read_file(path: str, max_lines: int | None = None, root=None) -> dict:
    base = _root(root)
    target = _resolve(base, path)
    if target is None:
        return _err(f"path {path!r} is outside the sandbox")
    if not target.is_file():
        return _err(f"file not found: {path}")
    lines = target.read_text(errors="replace").splitlines()
    shown = lines if max_lines is None else lines[: max(0, int(max_lines))]
    return {"ok": True, "path": path, "content": "\n".join(shown), "lines_returned": len(shown), "total_lines": len(lines),
            "truncated": len(shown) < len(lines)}


def write_file(path: str, content: str, root=None) -> dict:
    base = _root(root)
    target = _resolve(base, path)
    if target is None:
        return _err(f"path {path!r} is outside the sandbox")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return {"ok": True, "path": path, "bytes": len(content.encode())}


def edit_file(path: str, old_string: str, new_string: str, root=None) -> dict:
    """Replace exactly one occurrence of old_string; returns a short unified diff."""
    base = _root(root)
    target = _resolve(base, path)
    if target is None:
        return _err(f"path {path!r} is outside the sandbox")
    if not target.is_file():
        return _err(f"file not found: {path}")
    text = target.read_text()
    count = text.count(old_string)
    if count != 1:
        return _err(f"old_string must match exactly once, found {count} matches")
    updated = text.replace(old_string, new_string)
    target.write_text(updated)
    diff = list(difflib.unified_diff(text.splitlines(), updated.splitlines(), f"a/{path}", f"b/{path}", lineterm="", n=1))
    return {"ok": True, "path": path, "diff": "\n".join(diff[:20])}


def glob_files(pattern: str, root=None) -> dict:
    base = _root(root)
    matches = sorted(str(p.relative_to(base)) for p in base.glob(pattern) if p.is_file() and base in p.resolve().parents)
    return {"ok": True, "pattern": pattern, "count": len(matches), "files": matches}


def search_in_files(pattern: str, file_pattern: str = "*", root=None, max_results: int = 50) -> dict:
    base = _root(root)
    try:
        regex = re.compile(pattern)
    except re.error:
        regex = re.compile(re.escape(pattern))
    hits = []
    for path in sorted(base.rglob("*")):
        if not path.is_file() or not fnmatch.fnmatch(path.name, file_pattern):
            continue
        for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            if regex.search(line):
                hits.append({"file": str(path.relative_to(base)), "line": number, "text": line.strip()})
                if len(hits) >= max_results:
                    return {"ok": True, "pattern": pattern, "count": len(hits), "matches": hits, "truncated": True}
    return {"ok": True, "pattern": pattern, "count": len(hits), "matches": hits, "truncated": False}


def bash(command: str, root=None, auto_approve: bool = False, timeout: int = 10) -> dict:
    """Run a shell command inside the sandbox, but only when confirm_bash allows it."""
    decision = confirm_bash(command, auto_approve)
    if not decision["allowed"]:
        return {"ok": False, "blocked": True, "error": f"blocked by safety gate: {decision['reason']}"}
    done = subprocess.run(command, shell=True, cwd=_root(root), capture_output=True, text=True, timeout=timeout)
    return {"ok": done.returncode == 0, "returncode": done.returncode, "stdout": done.stdout[:MAX_BASH_OUTPUT],
            "stderr": done.stderr[:MAX_BASH_OUTPUT], "gate": decision["reason"]}


def file_toolbox(root=None, auto_approve: bool = False):
    """The six file tools as an agent Toolbox (JSON schemas + executors bound to one sandbox)."""
    import json

    from tool_agent import Tool, Toolbox

    def schema(props: dict, required: list[str]) -> dict:
        return {"type": "object", "properties": props, "required": required, "additionalProperties": False}

    def wrap(fn):
        return lambda args: json.dumps(fn(root=root, **args))

    return Toolbox([
        Tool("read_file", "Read a text file in the sandbox; max_lines limits how many lines are returned.",
             schema({"path": {"type": "string"}, "max_lines": {"type": "integer", "minimum": 1}}, ["path"]), wrap(read_file)),
        Tool("write_file", "Create or overwrite a text file in the sandbox.",
             schema({"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]), wrap(write_file)),
        Tool("edit_file", "Replace one exact occurrence of old_string with new_string; returns a short diff.",
             schema({"path": {"type": "string"}, "old_string": {"type": "string"}, "new_string": {"type": "string"}},
                    ["path", "old_string", "new_string"]), wrap(edit_file)),
        Tool("glob_files", "List files in the sandbox matching a glob pattern such as '*.py' or '**/*.txt'.",
             schema({"pattern": {"type": "string"}}, ["pattern"]), wrap(glob_files)),
        Tool("search_in_files", "Search file contents with a regex; file_pattern limits which files (for example '*.py').",
             schema({"pattern": {"type": "string"}, "file_pattern": {"type": "string"}}, ["pattern"]), wrap(search_in_files)),
        Tool("bash", "Run a shell command in the sandbox. Destructive or unlisted commands are blocked by the safety gate.",
             schema({"command": {"type": "string"}}, ["command"]), lambda args: json.dumps(bash(args["command"], root=root, auto_approve=auto_approve))),
    ])
