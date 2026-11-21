"""Append one new Summer 2027 internship from Jobright's GitHub lists to internships.md.

Prints the commit message on success. Exits with status 1 if there is
nothing new to add
"""
import re
import sys
import urllib.request
from datetime import datetime, timezone

SOURCES = {
    "Software-Engineer": "https://raw.githubusercontent.com/jobright-ai/2026-Software-Engineer-Internship/master/README.md",
    "Engineer": "https://raw.githubusercontent.com/jobright-ai/2026-Engineer-Internship/master/README.md",
}
CYBER = re.compile(r"cyber|security|infosec|penetration|soc analyst|threat|vulnerab", re.I)
ROBOTICS = re.compile(r"robot|autonom|mechatronic|drone|uav|perception|motion planning", re.I)
OTHER_TERM = re.compile(r"\b(fall|spring|winter)\b|\b20(?!27)\d\d\b", re.I)
LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
OUT = "internships.md"


def clean(text):
    """Strip HTML tags (e.g. </br>) and collapse whitespace."""
    text = re.sub(r"<[^>]*>", ", ", text)
    text = re.sub(r"\s+", " ", text)
    return re.sub(r"(,\s*)+", ", ", text).strip(" ,*")


def escape(text):
    """Make text safe inside markdown link text."""
    return text.replace("[", "\\[").replace("]", "\\]")


def fetch(url):
    for branch in ("master", "main"):
        try:
            with urllib.request.urlopen(url.replace("/master/", f"/{branch}/"), timeout=20) as r:
                return r.read().decode("utf-8")
        except Exception:
            continue
    return ""


def rows(source, text):
    company = ""
    for line in text.splitlines():
        if not line.startswith("| ") or line.startswith("| Company") or line.startswith("| -"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        m = LINK.search(cells[0])
        if cells[0] != "↳":
            company = m.group(1) if m else cells[0].strip("* ")
        m = LINK.search(cells[1])
        if not m:
            continue
        title, link = m.group(1).strip(), m.group(2).split("?")[0]
        if OTHER_TERM.search(title):
            continue  # not Summer 2027
        if CYBER.search(title):
            category = "Cybersecurity"
        elif ROBOTICS.search(title):
            category = "Robotics"
        elif source == "Software-Engineer":
            category = "Software Engineering"
        else:
            continue  # general engineering roles aren't wanted
        yield (category, escape(clean(company)), escape(clean(title)), link,
               clean(cells[2]), clean(cells[3]), clean(cells[4]))


def main():
    try:
        existing = open(OUT, encoding="utf-8").read()
    except FileNotFoundError:
        existing = "# Summer 2027 internships\n\nCybersecurity, Robotics and Software Engineering internships, collected from Jobright's public lists.\n\n"
        open(OUT, "w", encoding="utf-8").write(existing)

    # rare categories first, then newest-first within each category
    priority = {"Cybersecurity": 0, "Robotics": 1, "Software Engineering": 2}
    candidates = [r for s, u in SOURCES.items() for r in rows(s, fetch(u)) if r[3] not in existing and f"{r[1]} — [{r[2]}]" not in existing]
    candidates.sort(key=lambda r: priority[r[0]])  # stable sort keeps table order
    for category, company, title, link, location, model, posted in candidates[:1]:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        entry = f"- {day} · **{category}** · {company} — [{title}]({link}) · {location} · {model} · posted {posted}\n"
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(entry)
        print(f"Add internship: {company} — {title}"[:100])
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
