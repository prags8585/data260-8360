#!/usr/bin/env python3


import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
B = "http://localhost:8260"
J = "-H 'Content-Type: application/json'"
W = "-w '\\nHTTP %{http_code}\\n'"
PASSWORDS = {"reader1": "Reader#Pass2026", "writer1": "Writer#Pass2026", "moderator1": "Moderator#Pass2026"}
env = dict(os.environ)


def sh(command: str) -> str:
    return subprocess.run(["bash", "-c", command], capture_output=True, text=True, env=env, cwd=ROOT).stdout.rstrip("\n")


def token(username: str) -> str:
    out = subprocess.run(["curl", "-s", "-X", "POST", f"{B}/auth/login", "-H", "Content-Type: application/json",
                          "-d", json.dumps({"username": username, "password": PASSWORDS[username]})], capture_output=True, text=True).stdout
    return json.loads(out)["access_token"]


def block(label: str, command: str, pretty: bool = True) -> str:
    out = sh(command)
    if pretty and "\nHTTP" in out:
        body, code = out.rsplit("\nHTTP", 1)
        try:
            out = json.dumps(json.loads(body), indent=2) + "\nHTTP" + code
        except ValueError:
            pass
    print(f"\n## {label}\n$ {command}\n{out}")
    return out


def main() -> None:
    print(f"=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===  JWT auth evidence against {B}")
    env.update({"READER": token("reader1"), "WRITER": token("writer1"), "MODERATOR": token("moderator1")})
    env["EXPIRED"] = subprocess.run([sys.executable, "scripts/hw7_expired_token.py", "writer1"], capture_output=True, text=True, env={**env, "PYTHONPATH": "."}, cwd=ROOT).stdout.strip()
    login = lambda u, p: f"curl -s -X POST {B}/auth/login {J} -d '{{\"username\": \"{u}\", \"password\": \"{p}\"}}' {W}"  # noqa: E731
    block("login: valid credentials return a JWT", login("writer1", PASSWORDS["writer1"]))
    block("login: invalid credentials return 401", login("writer1", "wrong-password"))
    block("GET /auth/me without a token returns 401", f"curl -s {B}/auth/me {W}")
    block("GET /auth/me with an invalid token returns 401", f"curl -s {B}/auth/me -H 'Authorization: Bearer abc.def.ghi' {W}")
    block("GET /auth/me with an expired token returns 401", f"curl -s {B}/auth/me -H \"Authorization: Bearer $EXPIRED\" {W}")
    block("GET /auth/me with a valid token returns the identity and role", f"curl -s {B}/auth/me -H \"Authorization: Bearer $WRITER\" {W}")
    course = "{\"courseTitle\": \"JWT Demo Course\", \"courseCode\": \"DEMO-101\", \"seatsAvailable\": 20, \"instructorId\": 1}"
    create = lambda var: f"curl -s -X POST {B}/api/courses {J} -H \"Authorization: Bearer ${var}\" -d '{course}' {W}"  # noqa: E731
    block("create a course as a reader returns 403", create("READER"))
    out = block("create a course as a writer returns 201", create("WRITER"))
    course_id = json.loads(out.rsplit("\nHTTP", 1)[0])["id"]
    delete = lambda var: f"curl -s -X DELETE {B}/api/courses/{course_id} -H \"Authorization: Bearer ${var}\" {W}"  # noqa: E731
    block("delete a course as a writer returns 403", delete("WRITER"))
    block("delete a course as a moderator returns 204", delete("MODERATOR"), pretty=False)
    block("list courses with a valid token returns 200", f"curl -s '{B}/api/courses?limit=2' -H \"Authorization: Bearer $READER\" {W}")


if __name__ == "__main__":
    main()
