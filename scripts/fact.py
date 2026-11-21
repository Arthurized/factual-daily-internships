"""Append one new random fact to facts.md.

Facts containing a word from the FILTER_WORDS secret (one word per line,
case-insensitive) are skipped. Prints "add fact" on
success; exits with status 1 if no usable fact could be fetched.
"""
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

URL = "https://uselessfacts.jsph.pl/api/v2/facts/random?language=en"
OUT = "facts.md"

words = [w.strip() for w in os.environ.get("FILTER_WORDS", "").splitlines()
         if w.strip() and not w.strip().startswith("#")]
blocked = re.compile(r"\b(" + "|".join(map(re.escape, words)) + ")", re.I) if words else None

existing = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else "# Random facts\n\n"

for _ in range(10):
    try:
        req = urllib.request.Request(URL, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            fact = " ".join(json.load(r).get("text", "").split())
    except Exception:
        fact = ""
    if fact and fact not in existing and not (blocked and blocked.search(fact)):
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        with open(OUT, "w" if not os.path.exists(OUT) else "a", encoding="utf-8") as f:
            if not os.path.exists(OUT) or f.tell() == 0:
                f.write(existing)
            f.write(f"- {stamp} — {fact}\n")
        print("add fact")
        sys.exit(0)
    time.sleep(2)  # don't log skipped facts: they could reveal the filter
sys.exit(1)
