"""Append one new random fact to facts.md.

Facts come from the Useless Facts API; if it is down (or only returns facts
we already have), Wikipedia's "On this day" events are used instead.

Facts containing a word from the FILTER_WORDS secret (one word per line,
case-insensitive) are skipped. Prints "add fact" on
success; exits with status 1 if no usable fact could be fetched.
"""
import json
import os
import random
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

PRIMARY = "https://uselessfacts.jsph.pl/api/v2/facts/random?language=en"
BACKUP = "https://en.wikipedia.org/api/rest_v1/feed/onthisday/selected/{month:02d}/{day:02d}"
HEADERS = {"Accept": "application/json", "User-Agent": "daily-facts-bot/1.0"}
OUT = "facts.md"

words = [w.strip() for w in os.environ.get("FILTER_WORDS", "").splitlines()
         if w.strip() and not w.strip().startswith("#")]
blocked = re.compile(r"\b(" + "|".join(map(re.escape, words)) + ")", re.I) if words else None

existing = "# Random facts\n\n"
if os.path.exists(OUT):
    with open(OUT, encoding="utf-8") as f:
        existing = f.read()
now = datetime.now(timezone.utc)


def get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def one_line(text):
    return " ".join((text or "").split())


def usable(fact):
    return fact and fact not in existing and not (blocked and blocked.search(fact))


def from_primary():
    for attempt in range(10):
        try:
            fact = one_line(get_json(PRIMARY).get("text"))
        except Exception:
            fact = ""
        if usable(fact):
            return fact
        if attempt < 9:
            time.sleep(2)  # don't log skipped facts: they could reveal the filter
    return ""


def from_backup():
    try:
        events = get_json(BACKUP.format(month=now.month, day=now.day)).get("selected", [])
    except Exception:
        return ""
    if not isinstance(events, list):
        return ""
    random.shuffle(events)
    for e in events:
        if not isinstance(e, dict):
            continue
        year, text = e.get("year"), e.get("text")
        if isinstance(year, bool) or not isinstance(year, int) or not isinstance(text, str) or not text.strip():
            continue  # need a real year and some text
        text = re.sub(r"\s*\((pictured|depicted|shown)[^)]*\)", "", text)  # refers to Wikipedia's photo
        fact = one_line(f"On {now:%B} {now.day}, {year}: {text}")
        if usable(fact):
            return fact
    return ""


fact = from_primary() or from_backup()
if not fact:
    sys.exit(1)
with open(OUT, "a", encoding="utf-8") as f:
    if f.tell() == 0:
        f.write(existing)
    f.write(f"- {now:%Y-%m-%d %H:%M} — {fact}\n")
print("add fact")
