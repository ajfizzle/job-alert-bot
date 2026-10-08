"""
Finds which companies have remote, US-eligible jobs matching your titles.

Tries each company name on BOTH Greenhouse and Ashby, in parallel, and prints
only the boards that have at least one matching job. Sends no email and saves
nothing. Standard library only.

    python find_boards.py                  # uses the built-in list of names
    python find_boards.py my_names.txt     # uses your own list (one name per line)

A name is the part of a careers URL after boards.greenhouse.io/ or
jobs.ashbyhq.com/. Wrong or unused names are skipped silently.
Takes about 1-3 minutes.
"""

import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

# ---------------------------------------------------------------- your filters

TITLE_KEYWORDS = [
    "support engineer", "technical support engineer", "application support",
    "application support analyst", "support analyst", "developer support",
    "customer success engineer", "technical account manager",
    "technical account engineer", "solutions engineer", "solution engineer",
    "integration analyst", "integration support engineer", "escalation engineer",
    "platform support", "product support", "product support engineer",
]

EXCLUDE_WORDS = re.compile(r"\b(?:intern|internship|sales|director|vp)\b")

EXCLUDE_PATTERNS = [re.compile(p) for p in (
    r"^\s*(?:(?:senior|sr\.?|associate|group)\s+)?manager\b",
    r"\b(?:engineering|support|program|people|team)\s+manager\b",
    r"\bhead\s+of\b",
    r"\bsoftware\s+engineer",
    r"\bvice\s+president\b",
)]

REMOTE_WORDS = ("remote", "distributed")
ONSITE = re.compile(r"hybrid|on[-\s]?site|in[-\s]?office|in[-\s]?person")

US_OK = [r"\bus\b", r"\busa\b", r"u\.s\.", r"united states", r"worldwide",
         r"anywhere", r"north america", r"americas"]

NON_US = re.compile(
    r"\b(?:emea|apac|latam|europe|european|eu|uk|united kingdom|great britain|"
    r"england|scotland|ireland|germany|france|spain|italy|netherlands|poland|"
    r"portugal|sweden|norway|denmark|finland|estonia|latvia|lithuania|austria|"
    r"belgium|switzerland|czech|romania|bulgaria|hungary|greece|croatia|serbia|"
    r"ukraine|canada|ontario|quebec|british columbia|alberta|toronto|vancouver|"
    r"montreal|mexico|brazil|argentina|colombia|chile|peru|venezuela|uruguay|"
    r"costa rica|south america|latin america|india|pakistan|bangladesh|japan|"
    r"korea|singapore|australia|new zealand|israel|china|hong kong|taiwan|"
    r"vietnam|thailand|indonesia|malaysia|philippines|egypt|kenya|ghana|nigeria|"
    r"south africa|saudi arabia|qatar|uae|turkey)\b"
)

# ------------------------------------------------------------- candidate names

DEFAULT_NAMES = """
stripe datadog cloudflare gitlab elastic twilio okta mongodb samsara airtable
asana dropbox coinbase robinhood figma gusto hubspot zscaler pagerduty newrelic
fastly digitalocean vercel netlify hashicorp confluent databricks toast brex
carta amplitude mixpanel braze sentry circleci launchdarkly postman retool
zapier supabase notion plaid fivetran dbtlabs duolingo grammarly calendly
webflow squarespace linear ramp vanta posthog ashby rippling lattice gong
outreach segment mailchimp intercom zendesk freshworks front loom miro clickup
smartsheet canva lucid mural benchling flexport instacart doordash lyft reddit
discord pinterest medium substack patreon etsy shopify bigcommerce cockroachlabs
planetscale temporal grafana honeycomb cribl snyk jfrog 1password bitwarden
crowdstrike sentinelone tenable rapid7 sumologic chronosphere anaplan workiva
procore motive verkada anthropic openai scaleai mercury chime affirm klaviyo
attentive iterable heap pendo fullstory hotjar optimizely contentful sanity
algolia elasticpath commercetools sendbird stream agora bandwidth vonage
ringcentral dialpad aircall talkdesk five9 genesys nice zoom 8x8 slack
atlassian jetbrains github docker pulumi spacelift render railway fly
""".split()

HEADERS = {"User-Agent": "Mozilla/5.0 (JobAlertBot/1.0)"}

# --------------------------------------------------------------------- helpers


def get_json(url):
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read())
    except Exception:
        return None  # 404, timeout, bad JSON ... all mean "no usable board"


# Use the SAME title rules as your alert script when it is in this folder, so this tool
# and the daily email always agree (for example, no "technical account manager" here
# if you left it out of TITLE_KEYWORDS there). Otherwise fall back to the list below.
try:
    from ats_job_alert import title_matches as _alert_title_matches
except Exception:
    _alert_title_matches = None


def title_ok(title):
    if _alert_title_matches is not None:
        return _alert_title_matches(title or "")
    return _builtin_title_ok(title)


def _builtin_title_ok(title):
    t = (title or "").lower()
    return (
        any(k in t for k in TITLE_KEYWORDS)
        and not EXCLUDE_WORDS.search(t)
        and not any(p.search(t) for p in EXCLUDE_PATTERNS)
    )


def region_ok(location):
    t = (location or "").lower()
    if any(re.search(p, t) for p in US_OK):
        return True
    return not NON_US.search(t)


def scan_greenhouse(name):
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{name}/jobs")
    if not isinstance(data, dict):
        return None
    jobs = data.get("jobs", [])
    hits = []
    for j in jobs:
        title = j.get("title", "")
        loc = (j.get("location") or {}).get("name", "")
        low = loc.lower()
        if (
            title_ok(title)
            and any(w in low for w in REMOTE_WORDS)
            and not ONSITE.search(low)
            and region_ok(loc)
        ):
            hits.append((title, loc, str(j.get("updated_at", ""))[:10],
                         j.get("absolute_url", "")))
    return len(jobs), hits


def scan_ashby(name):
    data = get_json(
        f"https://api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true"
    )
    if not isinstance(data, dict):
        return None
    jobs = data.get("jobs", [])
    hits = []
    for j in jobs:
        title = j.get("title", "")
        loc = j.get("location") or ""
        low = loc.lower()
        workplace = str(j.get("workplaceType") or "").lower()
        remote = (
            j.get("isRemote") is True or any(w in low for w in REMOTE_WORDS)
        ) and workplace not in ("hybrid", "onsite") and not ONSITE.search(low)
        if j.get("isListed") is False:
            continue
        if title_ok(title) and remote and region_ok(loc):
            hits.append((title, loc, str(j.get("publishedAt", ""))[:10],
                         j.get("jobUrl", "")))
    return len(jobs), hits


def scan_lever(name):
    data = get_json(f"https://api.lever.co/v0/postings/{name}?mode=json")
    if data is None:
        data = get_json(f"https://api.eu.lever.co/v0/postings/{name}?mode=json")
    if not isinstance(data, list):
        return None
    hits = []
    for j in data:
        title = j.get("text", "")
        loc = (j.get("categories") or {}).get("location") or ""
        low = loc.lower()
        workplace = str(j.get("workplaceType") or "").lower()
        remote = workplace == "remote" or (
            workplace in ("", "unspecified") and any(w in low for w in REMOTE_WORDS)
        )
        if title_ok(title) and remote and not ONSITE.search(low) and region_ok(loc):
            created = j.get("createdAt")
            date = (datetime.fromtimestamp(created / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                    if isinstance(created, (int, float)) else "")
            hits.append((title, loc, date, j.get("hostedUrl", "")))
    return len(data), hits


def run(task):
    system, name = task
    scanner = {"Greenhouse": scan_greenhouse, "Ashby": scan_ashby, "Lever": scan_lever}[system]
    return system, name, scanner(name)


# ------------------------------------------------------------------------ main

def load_names():
    flags = [a for a in sys.argv[1:] if a.startswith("-")]
    files = [a for a in sys.argv[1:] if not a.startswith("-")]

    if flags:
        print(f"Note: this tool has no options, so {' '.join(flags)} was ignored. "
              "(--dry-run and -v belong to ats_job_alert.py.)\n")

    if files:
        try:
            with open(files[0], encoding="utf-8") as f:
                names = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            sys.exit(f"Cannot find the names file '{files[0]}'. "
                     "Run the tool with no arguments to use the built-in list.")
    else:
        names = DEFAULT_NAMES
    return list(dict.fromkeys(names))


def main():
    if _alert_title_matches is not None:
        print("Using the title rules from ats_job_alert.py.\n")
    else:
        print("ats_job_alert.py was not found next to this file; using the built-in title list.\n")
    names = load_names()
    tasks = [(s, n) for n in names for s in ("Greenhouse", "Ashby", "Lever")]
    print(f"Checking {len(names)} names on Greenhouse, Ashby and Lever "
          f"({len(tasks)} lookups). This takes a minute or two...\n")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(run, tasks))

    existing = [(s, n, r) for s, n, r in results if r is not None]
    winners = sorted(
        [(s, n, r) for s, n, r in existing if r[1]],
        key=lambda x: len(x[2][1]), reverse=True,
    )

    for system, name, (total, hits) in winners:
        print(f"[{system}] {name}: {total} open jobs, {len(hits)} fit your roles")
        for title, loc, date, url in hits:
            print(f"    - {title} | {loc} | {date}")
            print(f"      {url}")
        print()

    print("-" * 70)
    print(f"{len(existing)} of {len(tasks)} lookups found a real board; "
          f"{len(winners)} have at least one remote US-eligible match.")
    print("Dates are Greenhouse 'last updated' or Ashby 'published'; "
          "your alert applies the 41-day rule.\n")

    gh = [n for s, n, _ in winners if s == "Greenhouse"]
    ab = [n for s, n, _ in winners if s == "Ashby"]
    lv = [n for s, n, _ in winners if s == "Lever"]
    print("Paste into ats_job_alert.py (merge with your existing lists):")
    print(f"COMPANIES = {json.dumps(gh)}")
    print(f"ASHBY_BOARDS = {json.dumps(ab)}")
    print(f"LEVER_BOARDS = {json.dumps(lv)}")


if __name__ == "__main__":
    main()
