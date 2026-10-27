#!/usr/bin/env python3

import subprocess
from datetime import datetime

CONTAINER = "s8360-mysql"
QUERIES = [
    "DESCRIBE users;",
    "SELECT id, username, role, LEFT(password_hash, 29) AS password_hash_prefix, LENGTH(password_hash) AS hash_len FROM users;",
    "SHOW CREATE TABLE users\\G",
]


def main() -> None:
    print(f"=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===  MySQL users table ({CONTAINER}, database s8360_rel)")
    for q in QUERIES:
        cmd = f'docker exec {CONTAINER} mysql -uroot -phw4pass s8360_rel -t -e "{q}"'
        shown = cmd.replace("-phw4pass", "-p***")
        print(f"\n$ {shown}")
        out = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        print("\n".join(ln for ln in out.stdout.splitlines()).rstrip())


if __name__ == "__main__":
    main()
