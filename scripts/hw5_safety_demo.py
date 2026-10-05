#!/usr/bin/env python3
"""HW5 Part 5 I: one allowed and one blocked execute_tool call against the real database."""
import logging, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import execute_tool as et

logging.disable(logging.CRITICAL)
for label, inputs in [("ALLOWED", {"query": "database", "limit": 5}), ("BLOCKED", {"query": "student password", "limit": 5})]:
    print(f"--- {label} ---")
    print(f"execute_tool('search_courses', {inputs})")
    print(et.execute_tool("search_courses", inputs))
    print()
