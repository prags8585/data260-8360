#!/usr/bin/env python3
"""Fetches the HW3 Part 2 domain corpus: real public SJSU pages relevant
to the Campus Course Catalogue domain (DOMAIN_ID=0), extracts clean
visible text (not an AI summary), and saves one .txt per source to
corpus/hw03/. Also prints byte sizes for CORPUS_MANIFEST.json."""

import sys
import time
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

OUT = Path(__file__).resolve().parent.parent / "corpus/hw03"
OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) HW3-corpus-fetch/1.0"


def clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def main():
    entries = []
    for line in Path(sys.argv[1]).read_text().splitlines():
        name, url = line.split("|", 1)
        entries.append((name, url))

    for name, url in entries:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception as exc:
            print(f"FAILED {name}: {exc}")
            continue
        text = clean_text(html)
        out_path = OUT / f"{name}.txt"
        out_path.write_text(text)
        print(f"{name}: {len(text)} chars, {out_path.stat().st_size} bytes -> {out_path}")
        time.sleep(1)


if __name__ == "__main__":
    main()
