#!/usr/bin/env python3
"""HW9: add courses.views (the Redis counter is synced into it). Safe to run more than once."""
from sqlalchemy import inspect, text

from db import engine


def main() -> None:
    columns = [c["name"] for c in inspect(engine).get_columns("courses")]
    if "views" in columns:
        print("courses.views already exists")
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE courses ADD COLUMN views INT NOT NULL DEFAULT 0"))
    print("added courses.views INT NOT NULL DEFAULT 0")


if __name__ == "__main__":
    main()
