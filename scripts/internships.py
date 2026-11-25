"""Append one new Summer 2027 internship to internships.md.

Sources: SimplifyJobs' Summer 2027 listings and Jobright's GitHub lists.
Only roles open to Bachelor's students (or with no degree listed) are kept.

Prints the commit message on success. Exits with status 1 if there is
nothing new to add
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

SIMPLIFY = "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/{branch}/.github/scripts/listings.json"
SIMPLIFY_BRANCHES = ("dev", "main")
JOBRIGHT_BRANCHES = ("master", "main")
JOBRIGHT = {
    "Software-Engineer": "https://raw.githubusercontent.com/jobright-ai/2026-Software-Engineer-Internship/{branch}/README.md",
    "Engineer": "https://raw.githubusercontent.com/jobright-ai/2026-Engineer-Internship/{branch}/README.md",
}
CYBER = re.compile(r"cyber|security|infosec|penetration|soc analyst|threat|vulnerab", re.I)
ROBOTICS = re.compile(r"robot|autonom|mechatronic|drone|uav|perception|motion planning", re.I)
# Not Summer 2027: another season, or another year next to "Summer"/"Intern"/"Co-op".
# A graduation year ("Graduating 2028") is fine.
OTHER_TERM = re.compile(
    r"\b(fall|spring|winter|autumn)\b"
    r"|\bsummer\W{0,3}'?(?:20)?(?!27)\d\d\b"
    r"|\b20(?!27)\d\d\W{0,3}(summer|intern|internship|co-?op)\b", re.I)
# Education: a listing is excluded only when it EXPLICITLY says it is for graduate
# students (e.g. "PhD required", "Ph.D. students", "Currently pursuing a Master's",
# "graduate students only") and the same sentence offers no Bachelor's/undergrad option.
# Merely mentioning a degree ("Master's preferred", "Bachelor's/Master's/PhD required",
# a skill like "Master's in CS") never excludes a listing.
GRAD = r"(?:ph\.?\s?d\.?|doctora\w*|master(?:['’]?s)?|m\.?s\.?c?|mba|graduate)"
# the same, but "graduate" only as a degree ("graduate degree"), not the verb ("graduate by May")
GRAD_DEGREE = r"(?:ph\.?\s?d\.?|doctora\w*|master(?:['’]?s)?|m\.?s\.?c?|mba|graduate\s+(?:degree|program|school|studies|study))"
GRAD_REQUIRED = re.compile(
    rf"\b(?:enroll(?:ed|ment)\s+in|pursuing|working\s+towards?|candidate\s+for|studying\s+for)\s+(?:an?\s+|the\s+|your\s+)?{GRAD}(?![\w'’])"
    rf"|\b{GRAD_DEGREE}(?:(?!preferred|plus|nice to have|;|\.\s)[^;]){{0,60}}?\brequired\b"
    rf"|\b{GRAD}\s+(?:students?|candidates?)\b"
    rf"|\b(?:graduate|ph\.?\s?d\.?|doctoral|master(?:['’]?s)?)[- ]only\b"
    rf"|\bonly\s+(?:open\s+to\s+|for\s+)?{GRAD}(?![\w'’])", re.I)
GRAD_TITLE = re.compile(  # in a job title, any of these is explicit enough
    r"\bph\.?\s?d\b|\bdoctora|\bmasters\b|master['’]s|\bmba\b|\bgraduate\b|[-(]\s*m\.?s\.?\s*\)?\s*$", re.I)
BACHELOR_MENTION = re.compile(r"bachelor|undergrad|\bb\.?s\b|\bb\.?a\b|\bb\.s\.|\bb\.a\.", re.I)
LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
SIMPLIFY_SOFTWARE = {"Software", "Software Engineering"}
PRIORITY = {"Cybersecurity": 0, "Robotics": 1, "Software Engineering": 2}
OUT = "internships.md"
HEADER = ("# Summer 2027 internships\n\nCybersecurity, Robotics and Software Engineering "
          "internships, collected from SimplifyJobs' and Jobright's public lists.\n\n")
MAX_PAGE_CHECKS = 10  # new Jobright job pages downloaded per call, to stay polite
PAGE_TIMEOUT = 10  # seconds per Jobright job page
PAGE_TIME_BUDGET = 60  # seconds per call spent on Jobright job pages
MAX_PAGE_TIMEOUTS = 3  # after this many timeouts in a run, stop reading Jobright pages
EARLIEST = datetime(2024, 1, 1, tzinfo=timezone.utc)
CACHE = os.environ.get("SOURCE_CACHE")  # the workflow sets this so each run downloads once


def clean(text):
    """Strip HTML tags (e.g. </br>) and collapse whitespace. Non-text (e.g. null) becomes ''."""
    if not isinstance(text, str):
        return ""
    text = re.sub(r"<[^>]*>", ", ", text)
    text = re.sub(r"\s+", " ", text)
    return re.sub(r"(,\s*)+", ", ", text).strip(" ,*")


def escape(text):
    """Make text safe inside markdown link text."""
    return text.replace("[", "\\[").replace("]", "\\]")


def safe_url(url):
    """Make a URL safe inside a markdown link: (, ) and spaces would end or break it."""
    return url.strip().replace(" ", "%20").replace("(", "%28").replace(")", "%29")


def key(company, title):
    """Company + title with everything but letters and digits removed, for de-duplication."""
    return re.sub(r"[^a-z0-9]", "", (company + "|" + title).lower().replace("\\", ""))


_memory = {}  # stands in for SOURCE_CACHE when it isn't set (local runs)


def cache_path(url):
    return os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest()) if CACHE else None


def _flag(name):
    """Read a small per-run counter (kept in SOURCE_CACHE so it lasts the whole run)."""
    if not CACHE:
        return _memory.get(name, 0)
    try:
        with open(os.path.join(CACHE, name), encoding="utf-8") as f:
            return int(f.read() or 0)
    except (OSError, ValueError):
        return 0


def _bump(name):
    value = _flag(name) + 1
    if CACHE:
        with open(os.path.join(CACHE, name), "w", encoding="utf-8") as f:
            f.write(str(value))
    else:
        _memory[name] = value


def is_cached(url):
    """Already downloaded this run, or already failed this run."""
    path = cache_path(url)
    if not path:
        return url in _memory
    return os.path.exists(path) or os.path.exists(path + ".failed")


def is_timeout(error):
    return isinstance(error, TimeoutError) or isinstance(getattr(error, "reason", None), TimeoutError)


def fetch(url, timeout=30, remember_failure=False, timeout_counter="page-timeouts"):
    """Download url as text, cached for the run when SOURCE_CACHE is set.

    With remember_failure, a failed download isn't retried during the run,
    and timeouts are counted (in timeout_counter) so a slow site can be given up on.
    """
    path = cache_path(url)
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    if remember_failure and is_cached(url):
        return _memory.get(url, "")  # failed earlier this run
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = r.read().decode("utf-8")
    except Exception as e:
        if remember_failure:
            if path:
                open(path + ".failed", "w").close()
            else:
                _memory[url] = ""
            if is_timeout(e) and timeout_counter:
                _bump(timeout_counter)
        return ""
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    elif remember_failure:
        _memory[url] = text
    return text


REPO_TIMEOUT = 30  # seconds per list download from GitHub


def fetch_repo_file(url, branches, parse):
    """Download a list from the first branch whose copy `parse` accepts (returns non-None).

    A branch that fails to download is remembered for the run, so a slow or
    broken GitHub doesn't cost the timeout again on every call.
    """
    for branch in branches:
        text = fetch(url.format(branch=branch), timeout=REPO_TIMEOUT,
                     remember_failure=True, timeout_counter=None)
        if text:
            parsed = parse(text)
            if parsed is not None:
                return parsed
    return None


def parse_simplify(text):
    try:
        listings = json.loads(text)
    except ValueError:
        return None
    return listings if isinstance(listings, list) else None


def parse_jobright(text):
    return text if "| Company" in text else None  # a README with the listings table


def graduate_only(text):
    """Does this requirement explicitly limit the job to graduate students?

    "Applicants must be Ph.D. students", "Currently pursuing a Master's" -> True;
    "Bachelor's/Master's/PhD required", "Master's preferred", "Master's in CS" -> False.
    """
    return bool(GRAD_REQUIRED.search(text)) and not BACHELOR_MENTION.search(text)


def graduate_title(title):
    """A title like 'PhD Intern', 'Graduate Intern' or '... - MS' (but not 'Bachelor's & Master's')."""
    return bool(GRAD_TITLE.search(title)) and not BACHELOR_MENTION.search(title)


def category_for(title, software):
    if CYBER.search(title):
        return "Cybersecurity"
    if ROBOTICS.search(title):
        return "Robotics"
    return "Software Engineering" if software else None


def simplify_rows():
    listings = fetch_repo_file(SIMPLIFY, SIMPLIFY_BRANCHES, parse_simplify)
    for x in listings or []:
        if not isinstance(x, dict):
            continue
        if not (x.get("active") and x.get("is_visible", True)):
            continue
        terms = x.get("terms")
        if not isinstance(terms, list) or "Summer 2027" not in terms:
            continue
        degrees = x.get("degrees")
        degrees = degrees if isinstance(degrees, list) else []
        if degrees and "Bachelor's" not in degrees:
            continue  # graduate-only role
        title, company, url = clean(x.get("title")), clean(x.get("company_name")), x.get("url")
        if not title or not company or not isinstance(url, str) or not url.startswith("http"):
            continue
        if graduate_title(title):
            continue
        category = category_for(title, x.get("category") in SIMPLIFY_SOFTWARE)
        if not category:
            continue
        locations = x.get("locations")
        locations = [l for l in map(clean, locations if isinstance(locations, list) else []) if l]
        location = ", ".join(locations[:3]) + (f" +{len(locations) - 3} more" if len(locations) > 3 else "")
        yield {
            "category": category, "company": company, "title": title,
            "link": safe_url(url), "location": location, "model": "",
            "posted": valid_date(x.get("date_posted")), "source": "SimplifyJobs",
        }


def plausible(d):
    """A posting date must be real: not in the future and not before 2024."""
    now = datetime.now(timezone.utc)
    return d if EARLIEST <= d <= now + timedelta(days=1) else None


def valid_date(stamp):
    """Simplify's Unix timestamp -> datetime, or None if it is missing or invalid."""
    if isinstance(stamp, bool) or not isinstance(stamp, (int, float)):
        return None
    try:
        return plausible(datetime.fromtimestamp(stamp, timezone.utc))
    except (OverflowError, OSError, ValueError):
        return None


def jobright_date(text, now):
    """'Nov 20' -> datetime, or None if it can't be read. Jobright tables omit the year."""
    for year in (now.year, now.year - 1):  # most recent such date that isn't in the future
        try:
            d = datetime.strptime(f"{text} {year}", "%b %d %Y").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if d <= now + timedelta(days=1):
            return plausible(d)
    return None


def jobright_rows(now):
    for source, url in JOBRIGHT.items():
        company = ""
        for line in (fetch_repo_file(url, JOBRIGHT_BRANCHES, parse_jobright) or "").splitlines():
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
            title, link = clean(m.group(1)), safe_url(m.group(2).split("?")[0])
            if OTHER_TERM.search(title):
                continue  # not Summer 2027
            if graduate_title(title):
                continue
            category = category_for(title, source == "Software-Engineer")
            if not category:
                continue  # general engineering roles aren't wanted
            yield {
                "category": category, "company": clean(company), "title": title, "link": link,
                "location": clean(cells[2]), "model": clean(cells[3]),
                "posted": jobright_date(clean(cells[4]), now), "source": "Jobright",
            }


def _strings(value):
    """Every piece of text inside a JSON value (strings in lists/dicts, at any depth)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    return []  # null, numbers, booleans


def must_have_items(page, job_id):
    """The must-have qualifications of job `job_id`, as a list of strings.

    Read only from that job's own record in the page's embedded data
    (__NEXT_DATA__ -> props.pageProps.dataSource.jobResult), so nothing from
    other jobs on the page is mixed in. Jobright keeps the requirements in two
    places, as a list of sentences (qualifications.mustHave) and as a structured
    object (detailQualifications.mustHave); both are read. An empty list means
    none are listed; None means the page couldn't be read or is for another job.
    """
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
        job = data["props"]["pageProps"]["dataSource"]["jobResult"]
    except (ValueError, KeyError, TypeError):
        return None
    if not isinstance(job, dict) or job.get("jobId") != job_id:
        return None
    items = []
    for section in ("qualifications", "detailQualifications"):
        block = job.get(section)
        if isinstance(block, dict):
            items += _strings(block.get("mustHave"))
    return items


def requires_graduate(items):
    """Any single requirement asking for a graduate degree without a Bachelor's option,
    e.g. "Bachelor's completed" + "Currently pursuing a Master's" -> True."""
    return any(graduate_only(i) for i in items)


def job_id(link):
    m = re.search(r"/jobs/info/([0-9a-f]{24})\b", link)
    return m.group(1) if m else None


def needs_graduate_degree(link):
    """True/False from a Jobright job page's must-have qualifications; None if unknown."""
    jid = job_id(link)
    if not jid:
        return None
    page = fetch(link, timeout=PAGE_TIMEOUT, remember_failure=True)
    if not page:
        return None
    items = must_have_items(page, jid)
    if items is None:
        return None
    return requires_graduate(items)


def main():
    try:
        with open(OUT, encoding="utf-8") as f:
            existing = f.read()
    except FileNotFoundError:
        existing = HEADER
        with open(OUT, "w", encoding="utf-8") as f:
            f.write(existing)
    seen_links = set(re.findall(r"\]\((https?://[^)\s]+)\)", existing))
    seen_keys = {key(c, t) for c, t in re.findall(r"· ([^·\n]+?) — \[(.+?)\]\(", existing)}

    now = datetime.now(timezone.utc)
    candidates, batch_keys = [], set()
    for row in list(simplify_rows()) + list(jobright_rows(now)):  # Simplify wins ties
        k = key(row["company"], row["title"])
        if row["link"] in seen_links or k in seen_keys or k in batch_keys:
            continue
        batch_keys.add(k)
        candidates.append(row)
    # rare categories first, then newest first
    candidates.sort(key=lambda r: (PRIORITY[r["category"]], r["posted"] is None,
                                   -(r["posted"] or EARLIEST).timestamp()))

    downloads, started = 0, time.monotonic()
    for r in candidates:
        if r["source"] == "Jobright":
            if not is_cached(r["link"]):  # pages already read (or failed) this run are free
                out_of_time = time.monotonic() - started > PAGE_TIME_BUDGET
                if (downloads >= MAX_PAGE_CHECKS or out_of_time
                        or _flag("page-timeouts") >= MAX_PAGE_TIMEOUTS):
                    continue  # Jobright is slow or the budget is spent: Simplify rows only
                downloads += 1
            if needs_graduate_degree(r["link"]) is not False:
                continue  # graduate-only, or couldn't tell: skip for now
        posted = "posted " + r["posted"].strftime("%b %d") if r["posted"] else ""
        details = " · ".join(p for p in (r["location"], r["model"], posted, "via " + r["source"]) if p)
        entry = (f"- {now:%Y-%m-%d} · **{r['category']}** · {escape(r['company'])} — "
                 f"[{escape(r['title'])}]({r['link']}) · {details}\n")
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(entry)
        print(f"Add internship: {r['company']} — {r['title']}"[:100])
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
