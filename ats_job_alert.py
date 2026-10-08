#!/usr/bin/env python3
"""
Daily remote job alert.

Searches Greenhouse boards and a few remote job boards for matching roles,
emails anything new, then remembers what it sent.

Setup (environment variables):
    JOB_ALERT_EMAIL_FROM      Gmail address to send from
    JOB_ALERT_EMAIL_PASSWORD  Gmail App Password
    JOB_ALERT_EMAIL_TO        Comma-separated recipients (defaults to FROM)

Usage:
    python ats_job_alert.py              # search, email, save
    python ats_job_alert.py --dry-run    # search and print the email; send/save nothing
    python ats_job_alert.py --dry-run -v # also show every job that was dropped, and why
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import logging
import os
import re
import smtplib
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, Iterator, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


# =====================================================
# SETTINGS
# =====================================================

# Defaults used when the JOB_ALERT_EMAIL_FROM / JOB_ALERT_EMAIL_TO environment
# variables are not set. The Gmail App Password is NEVER stored here: it must be
# in the JOB_ALERT_EMAIL_PASSWORD environment variable.
DEFAULT_EMAIL_FROM = ""   # leave empty: set JOB_ALERT_EMAIL_FROM instead
DEFAULT_EMAIL_TO: list[str] = []   # leave empty: set JOB_ALERT_EMAIL_TO instead (defaults to FROM)

BASE_DIR = Path(__file__).resolve().parent  # files live next to the script, not the cwd
SEEN_FILE = BASE_DIR / "seen_jobs.txt"
CSV_FILE = BASE_DIR / "jobs.csv"
LOG_FILE = BASE_DIR / "job_alert.log"

TITLE_KEYWORDS = [
    "support engineer",
    "technical support engineer",
    "application support",
    "application support analyst",
    "support analyst",
    "developer support",
    "customer success engineer",
    "customer support engineer",
    "developer support engineer",
    "telecom support engineer",
    "technical support specialist",
    "technical account engineer",
    "solutions engineer",
    "solutions analyst",
    "integration analyst",
    "integration support engineer",
    "escalation engineer",
    "platform support",
    "product support",
    "product support engineer",
]

# Solutions Engineer / Solutions Analyst roles are often pre-sales (supporting the sales
# team) rather than customer support. True = keep them (as before), False = drop them.
INCLUDE_SOLUTIONS_ENGINEERS = True

# Titles containing any of these WORDS are dropped (whole-word match, so
# "intern" will not hit "international"). Edit freely.
EXCLUDE_TITLE_WORDS = ["intern", "internship", "sales", "director", "vp"]

# Titles matching any of these patterns are dropped. They remove people-manager
# roles but keep "Technical Account Manager".
EXCLUDE_TITLE_PATTERNS = [
    r"^\s*(?:(?:senior|sr\.?|associate|group)\s+)?manager\b",  # "Manager II, Support ..."
    r"\b(?:engineering|support|program|people|team)\s+manager\b",
    r"\bhead\s+of\b",
    r"\bsoftware\s+engineer",          # "Ads Data Solutions Engineering" software roles
    r"\bvice\s+president\b",          # "Regional Vice President, ..."
]

# Only include jobs posted within this many days
DAYS_BACK = 41

# Drop jobs whose listed USD pay tops out below this. Jobs with no pay listed
# (or pay in another currency) are kept.
MIN_SALARY = 95000

# Jobright needs your login, so it is a click-through link in the email, not a
# searched source. In your browser, open Jobright with your filters applied
# (e.g. "Support Engineer, US"), then paste that page's address here.
JOBRIGHT_URL = "https://jobright.ai/"

# Greenhouse board names. Set to [] to skip Greenhouse.
COMPANIES = [
    "datadog", "cloudflare", "elastic", "gitlab",
    "nice", "cribl", "zscaler", "twilio", "stripe", "jetbrains",
    "singlestore", "volexity",   # found through your Jobright links
]
# Boards that had only pre-sales "Solutions Engineer" roles (add if you want them):
#   launchdarkly, jfrog, databricks, toast, fivetran, webflow, intercom, algolia

# Ashby board names: the last part of jobs.ashbyhq.com/<name>. Copy the spelling
# from the URL exactly. Set to [] to skip Ashby. (These are just examples; a wrong
# name prints a "not found" warning and is skipped.)
ASHBY_BOARDS = ["ashby", "linear", "sanity", "1password", "clickup", "supabase", "plaid", "mdcalc"]

# Lever board names: the last part of jobs.lever.co/<name>. Set to [] to skip Lever.
# (Examples only: a wrong name prints a "not found" warning and is skipped. Run
# find_boards.py to discover more companies that use Lever.)
LEVER_BOARDS = ["jumpcloud", "truv", "redoxengine"]  # names seen in real jobs.lever.co links

# Remote-first companies whose jobs often list only a country ("United States")
# with no word "remote". For these only, a country-only location counts as remote.
COUNTRY_ONLY_OK_COMPANIES = {"elastic", "singlestore", "volexity"}  # Jobright confirms these list remote roles as just "United States"

USE_REMOTIVE = True
USE_REMOTEOK = True
USE_WEWORKREMOTELY = True

# Jobright needs your login, so it is NOT fetched live. Instead, export your
# Jobright results yourself (F12 -> Network -> the "jobs?refresh=true..." request ->
# Response -> Copy response), paste them into jobright.json next to this script, and
# the jobs are run through the same filters as every other source.
USE_JOBRIGHT_FILE = True
JOBRIGHT_FILE = BASE_DIR / "jobright.json"
JOBRIGHT_STALE_DAYS = 3  # warn when the export is older than this

# JobAssist works the same way: export the jobs response from your own logged-in
# browser (F12 -> Network -> the request to api.jobassist.com that returns the job
# list) and save it as jobassist.json next to this script.
USE_JOBASSIST_FILE = True
JOBASSIST_FILE = BASE_DIR / "jobassist.json"
JOBASSIST_STALE_DAYS = 3
# Your JobAssist search is filtered to remote jobs. If a record has no remote/hybrid
# field at all, treat it as remote (True) or skip it (False).
JOBASSIST_ASSUME_REMOTE = True

# TheirStack is the job-data company JobAssist's listings come from. It has a real API
# (theirstack.com): sign up, copy your API key, and set it in PowerShell with
#     $env:THEIRSTACK_API_KEY = "your-key"
# It searches by title across ALL companies. Every job it returns costs 1 credit, and
# the free plan gives only a small monthly allowance, so these limits protect it.
USE_THEIRSTACK = True               # does nothing unless THEIRSTACK_API_KEY is set
THEIRSTACK_MAX_JOBS_PER_RUN = 25    # most jobs requested per run (1 credit each; the free plan allows 25 max)
THEIRSTACK_MAX_AGE_DAYS = 7         # only jobs posted in the last N days
THEIRSTACK_MONTHLY_BUDGET = 150     # stop asking once this many credits are used in a month
THEIRSTACK_CACHE_HOURS = 12         # reuse saved results for repeat runs (no credits)
THEIRSTACK_DIRECT_EMPLOYERS_ONLY = True  # skip recruiting agencies (cuts noise and wasted credits)
THEIRSTACK_USAGE_FILE = BASE_DIR / "theirstack_usage.json"
THEIRSTACK_CACHE_FILE = BASE_DIR / "theirstack_cache.json"

# Workable: (1) its own public job search across ALL the companies that use Workable,
# and (2) specific companies: the name in apply.workable.com/<name>. No key needed.
USE_WORKABLE_SEARCH = True
WORKABLE_SEARCH_QUERIES = [
    "support engineer", "technical support", "application support",
    "customer support engineer", "escalation engineer", "integration support",
    "technical support engineer", "product support engineer",
    "technical support specialist", "application support engineer",
]
WORKABLE_SEARCH_PAGES = 2           # pages of ~20 jobs per query
WORKABLE_BOARDS: list[str] = []     # e.g. ["huggingface"]; a wrong name just prints a warning

# Keep only regions matching these (blank or plain "Remote" is also kept).
OK_REGION_PATTERNS = [
    r"\bus\b", r"\busa\b", r"u\.s\.", r"united states", r"worldwide",
    r"anywhere", r"north america", r"americas",
]

# Networking
USER_AGENT = "JobAlertBot/1.0"
REQUEST_TIMEOUT = 15
RETRIES = 3
BACKOFF_SECONDS = 1.5
GREENHOUSE_DETAIL_DELAY = 0.2  # polite pause between per-job detail requests

NOW = datetime.now(timezone.utc)
CUTOFF_DATE = NOW - timedelta(days=DAYS_BACK)

log = logging.getLogger("job_alert")


# =====================================================
# DATA MODEL
# =====================================================

@dataclass
class Job:
    company: str
    title: str
    url: str
    location: str
    source: str
    posted_dt: Optional[datetime]
    posted_label: str = "Posted"
    pay: str = "Not listed"
    pay_max: Optional[int] = None
    date_found: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    )

    @property
    def posted(self) -> str:
        if not self.posted_dt:
            return "Date unknown"
        days_ago = (NOW - self.posted_dt).days
        return f"{self.posted_label} {self.posted_dt:%Y-%m-%d} ({days_ago} days ago)"

    @property
    def dedupe_key(self) -> tuple[str, str]:
        return (self.title.lower(), self.company.lower())

    def as_row(self) -> dict:
        return {
            "company": self.company, "title": self.title, "url": self.url,
            "location": self.location, "source": self.source,
            "posted": self.posted, "pay": self.pay, "date_found": self.date_found,
        }


@dataclass
class EmailConfig:
    sender: str
    recipients: list[str]
    password: str


# =====================================================
# GENERIC HELPERS
# =====================================================

def text(value) -> str:
    """Safe string: None becomes '', everything else is stripped str()."""
    return "" if value is None else str(value).strip()


def to_int(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def http_get(url: str, timeout: int = REQUEST_TIMEOUT) -> bytes:
    """GET with retries and exponential backoff on transient failures."""
    last: Exception = RuntimeError("no attempts made")

    for attempt in range(1, RETRIES + 1):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except HTTPError as ex:
            if ex.code < 500 and ex.code != 429:
                raise  # 4xx (except 429) will not fix itself
            last = ex
        except (URLError, TimeoutError, ConnectionError) as ex:
            last = ex

        if attempt < RETRIES:
            time.sleep(BACKOFF_SECONDS * 2 ** (attempt - 1))

    raise last


def fetch_json(url: str):
    return json.loads(http_get(url))


def parse_date(value) -> Optional[datetime]:
    value = text(value)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def sort_newest(jobs: list[Job]) -> None:
    oldest = datetime.min.replace(tzinfo=timezone.utc)
    jobs.sort(key=lambda j: j.posted_dt or oldest, reverse=True)


# =====================================================
# URL NORMALIZING + SEEN-JOB STORE
# =====================================================

_TRACKING_PARAMS = {"ref", "source", "src", "fbclid", "gclid"}


def normalize_url(url: str) -> str:
    """
    Strip tracking params and fragments so the same job always has the same URL.
    Other params are kept on purpose: Greenhouse company-hosted pages identify
    the job with ?gh_jid=...
    """
    url = text(url)
    if not url:
        return ""
    parts = urlsplit(url)
    query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not (k.lower().startswith("utm_") or k.lower() in _TRACKING_PARAMS)
    ]
    path = parts.path.rstrip("/") or parts.path
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), ""))


def load_seen() -> set[str]:
    if not SEEN_FILE.exists():
        return set()
    with open(SEEN_FILE, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def save_seen(urls: list[str], seen: set[str]) -> None:
    new = [u for u in dict.fromkeys(urls) if u and u not in seen]
    if not new:
        return
    with open(SEEN_FILE, "a", encoding="utf-8") as f:
        for url in new:
            f.write(url + "\n")
    seen.update(new)


SENT_KEY_DAYS = 120  # a repeat of the same title+company is ignored for this long


def seen_key(job) -> str:
    return "key::" + job.title.lower().strip() + "||" + job.company.lower().strip()


def keys_from_csv() -> set[str]:
    """Title+company of jobs already emailed, read from jobs.csv (recent rows only)."""
    keys: set[str] = set()
    horizon = (NOW - timedelta(days=SENT_KEY_DAYS)).strftime("%Y-%m-%d")
    try:
        with open(CSV_FILE, "r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                title = (row.get("title") or "").lower().strip()
                company = (row.get("company") or "").lower().strip()
                if title and (row.get("date_found") or "9999")[:10] >= horizon:
                    keys.add(f"key::{title}||{company}")
    except OSError:
        pass
    return keys


def is_seen(raw_url: str, norm_url: str, seen: set[str]) -> bool:
    # Check both forms so entries saved by older versions (raw URLs) still match.
    return raw_url in seen or norm_url in seen


# =====================================================
# FILTERS
# =====================================================

_EXCLUDE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in EXCLUDE_TITLE_WORDS) + r")\b"
)
_EXCLUDE_PATTERNS_RE = [re.compile(p) for p in EXCLUDE_TITLE_PATTERNS]

_ONSITE = r"(?:hybrid|on[-\s]?site|in[-\s]?office|in[-\s]?person)"
_NOT_REMOTE_RE = re.compile(rf"\b{_ONSITE}\b")
_NEGATED_RE = re.compile(rf"\b(?:no|not|without)\s+{_ONSITE}\b")  # "no on-site"

REMOTE_WORDS = ["remote", "distributed"]  # Cloudflare labels remote roles "Distributed"

_COUNTRY_ONLY = re.compile(
    r"(united states|usa|u\.s\.a?\.?|us|north america|americas)(\s*[-,(].*)?"
)


_SOLUTIONS_RE = re.compile(r"\bsolutions?\s+(?:engineer|analyst)")


def title_matches(title: str) -> bool:
    t = title.lower()

    return (
        any(k in t for k in TITLE_KEYWORDS)
        and not _EXCLUDE_RE.search(t)
        and not any(p.search(t) for p in _EXCLUDE_PATTERNS_RE)
        and not title_names_non_us(t)
        and (INCLUDE_SOLUTIONS_ENGINEERS or not _SOLUTIONS_RE.search(t))
    )


def looks_on_site(value: str) -> bool:
    """
    True if the text says hybrid / onsite / in-office.
    """
    cleaned = _NEGATED_RE.sub("", value.lower())
    return bool(_NOT_REMOTE_RE.search(cleaned))


def is_remote(location: str, company: str = "") -> bool:
    t = text(location).lower()

    if looks_on_site(t):
        return False

    if any(word in t for word in REMOTE_WORDS):
        return True

    if company.lower() in COUNTRY_ONLY_OK_COMPANIES:
        return bool(_COUNTRY_ONLY.fullmatch(t))

    return False


def region_ok(region: str) -> bool:
    t = text(region).lower()

    if not t or t == "remote":
        return True

    return any(
        re.search(p, t)
        for p in OK_REGION_PATTERNS
    )


_NON_US_RE = re.compile(
    r"\b(?:emea|apac|latam|dach|nordics|benelux|anz|mena|asean|europe|european|eu|uk|"
    r"united kingdom|great britain|england|scotland|wales|ireland|germany|france|spain|"
    r"italy|netherlands|poland|portugal|sweden|norway|denmark|finland|estonia|latvia|"
    r"lithuania|austria|belgium|switzerland|czech|romania|bulgaria|hungary|greece|"
    r"croatia|serbia|ukraine|cyprus|luxembourg|slovakia|slovenia|canada|ontario|quebec|"
    r"british columbia|alberta|mexico|brazil|argentina|colombia|chile|peru|venezuela|"
    r"uruguay|costa rica|south america|latin america|india|pakistan|bangladesh|japan|"
    r"korea|singapore|australia|new zealand|israel|china|hong kong|taiwan|vietnam|"
    r"thailand|indonesia|malaysia|philippines|egypt|kenya|ghana|nigeria|south africa|"
    r"saudi arabia|qatar|uae|turkey|"
    r"sydney|melbourne|brisbane|canberra|tokyo|osaka|london|dublin|berlin|munich|paris|"
    r"madrid|barcelona|amsterdam|lisbon|warsaw|krakow|prague|vienna|zurich|stockholm|"
    r"oslo|copenhagen|helsinki|tallinn|riga|vilnius|bangalore|bengaluru|mumbai|delhi|"
    r"hyderabad|pune|mohali|sao paulo|são paulo|mexico city|cdmx|buenos aires|bogota|"
    r"lima|santiago|tel aviv|dubai|seoul|shanghai|beijing|manila|jakarta|kuala lumpur|"
    r"bangkok|hanoi|cairo|lagos|nairobi|johannesburg|cape town|toronto|vancouver|"
    r"montreal)\b"
)


def remote_region_ok(location: str) -> bool:
    t = text(location).lower()

    if any(
        re.search(p, t)
        for p in OK_REGION_PATTERNS
    ):
        return True

    return not _NON_US_RE.search(t)


US_COUNTRY_NAMES = {"united states", "united states of america", "usa", "us", "u.s."}


def title_names_non_us(title: str) -> bool:
    """True for titles like 'Support Engineer (EMEA)' or 'Solutions Engineer, Japan'."""
    t = title.lower()

    if any(re.search(p, t) for p in OK_REGION_PATTERNS):
        return False

    return bool(_NON_US_RE.search(t))


_FULL = re.compile(
    r"\$\s?(\d{1,3}(?:,\d{3})+)"
)

_K = re.compile(
    r"\$\s?(\d{2,3})\s?(?:[-–]\s?\$?\s?(\d{2,3}))?\s?[kK]\b"
)


def parse_amounts(value: str) -> list[int]:
    value = text(value)

    amounts = [
        int(m.replace(",", ""))
        for m in _FULL.findall(value)
    ]

    for a, b in _K.findall(value):
        amounts.append(int(a) * 1000)

        if b:
            amounts.append(int(b) * 1000)

    return [
        v for v in amounts
        if 30000 <= v <= 600000
    ]


def salary_indicator(pay_max: Optional[int]) -> str:
    """Return a concise label for the salary relative to the configured target."""
    if pay_max is None:
        return "Not listed"
    return "Meets target" if pay_max >= MIN_SALARY else "Below target"


# =====================================================
# GREENHOUSE
# =====================================================

GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards"


def get_posted_date(company: str, job_id, fallback) -> tuple[Optional[datetime], str]:
    """
    The job LIST only has 'updated_at' (changes on every edit). The job DETAIL
    has 'first_published', the real posting date.
    """
    try:
        time.sleep(GREENHOUSE_DETAIL_DELAY)
        detail = fetch_json(f"{GREENHOUSE_API}/{company}/jobs/{job_id}")

        first = parse_date(detail.get("first_published"))
        if first:
            return first, "Posted"
    except Exception as ex:
        log.debug("detail lookup failed for %s/%s: %s", company, job_id, ex)

    return parse_date(fallback), "Last updated"


def search_greenhouse(seen: set[str]) -> tuple[list[Job], list[str]]:
    jobs: list[Job] = []
    too_old: list[str] = []

    for company in COMPANIES:
        stats: Counter = Counter()

        try:
            data = fetch_json(f"{GREENHOUSE_API}/{company}/jobs")

            for item in data.get("jobs", []):
                stats["total"] += 1

                title = text(item.get("title"))
                if not title_matches(title):
                    continue
                stats["title"] += 1

                raw_url = text(item.get("absolute_url"))
                if not raw_url:
                    continue
                url = normalize_url(raw_url)

                location = text((item.get("location") or {}).get("name")) or "Unknown"
                if not is_remote(location, company) or not remote_region_ok(location):
                    stats["not_remote"] += 1
                    log.debug("dropped (not remote / non-US region): %s | %s", title, location)
                    continue

                if is_seen(raw_url, url, seen):
                    stats["seen"] += 1
                    continue

                posted_dt, label = get_posted_date(
                    company, item.get("id"), item.get("updated_at")
                )

                pay = "Not listed"
                pay_max = None

                try:
                    detail = fetch_json(
                        f"{GREENHOUSE_API}/{company}/jobs/{item.get('id')}"
                    )

                    content = detail.get("content", "")

                    amounts = parse_amounts(content)

                    if amounts:
                        pay_max = max(amounts)

                    if len(amounts) >= 2:
                        pay = f"${min(amounts):,} - ${max(amounts):,}"
                    elif amounts:
                        pay = f"${amounts[0]:,}"

                except Exception:
                    pass

                job = Job(
                    company=company,
                    title=title,
                    url=url,
                    location=location,
                    source="Greenhouse",
                    posted_dt=posted_dt,
                    posted_label=label,
                    pay=pay,
                    pay_max=pay_max,
                )

                if job.posted_dt and job.posted_dt < CUTOFF_DATE:
                    stats["old"] += 1
                    too_old.append(url)
                    continue

                stats["kept"] += 1
                jobs.append(job)

        except Exception as ex:
            log.error("%s failed: %s", company, ex)
            continue

        log.info(
            "  %s: %d open | %d title matches | %d not remote | %d already sent | "
            "%d older than %d days | %d listed",
            company, stats["total"], stats["title"], stats["not_remote"],
            stats["seen"], stats["old"], DAYS_BACK, stats["kept"],
        )

    return jobs, too_old


# =====================================================
# ASHBY
# =====================================================

ASHBY_API = "https://api.ashbyhq.com/posting-api/job-board"


def search_ashby(seen: set[str], known_keys: set) -> tuple[list[Job], list[str]]:
    """
    Ashby's public Job Postings API returns a board's whole job list in one
    request (no login or key), including pay when includeCompensation=true.
    """
    jobs: list[Job] = []
    too_old: list[str] = []
    batch_keys = set(known_keys)

    for board in ASHBY_BOARDS:
        stats: Counter = Counter()

        try:
            data = fetch_json(f"{ASHBY_API}/{board}?includeCompensation=true")

            for item in data.get("jobs", []):
                stats["total"] += 1

                title = text(item.get("title"))
                if not title_matches(title):
                    continue
                stats["title"] += 1

                if item.get("isListed") is False:
                    continue

                raw_url = text(item.get("jobUrl") or item.get("applyUrl"))
                if not raw_url:
                    continue
                url = normalize_url(raw_url)

                location = text(item.get("location")) or "Remote"
                workplace = text(item.get("workplaceType")).lower()  # remote / hybrid / onsite

                # Ashby's isRemote flag is unreliable (hybrid jobs can carry it), so
                # trust workplaceType first and the location text second.
                remote = workplace == "remote" or (not workplace and is_remote(location))
                # A remote role can still be limited to a region ("Remote, Canada",
                # "London, United Kingdom"), so check the region on every job.
                region_bad = not remote_region_ok(location)

                address = (item.get("address") or {}).get("postalAddress") or {}
                country = text(address.get("addressCountry"))

                if (
                    country
                    and country.lower() not in US_COUNTRY_NAMES
                    and not any(re.search(p, location.lower()) for p in OK_REGION_PATTERNS)
                ):
                    stats["not_remote"] += 1
                    log.debug("dropped (job address in %s): %s | %s", country, title, location)
                    continue

                if (
                    not remote
                    or workplace in ("hybrid", "onsite")
                    or looks_on_site(location)
                    or region_bad
                ):
                    stats["not_remote"] += 1
                    log.debug("dropped (not remote): %s | %s", title, location)
                    continue

                comp = item.get("compensation") or {}
                pay = text(
                    comp.get("compensationTierSummary")
                    or comp.get("scrapeableCompensationSalarySummary")
                )
                pay_max = max(parse_amounts(pay), default=None)

                if pay_max and pay_max < MIN_SALARY:
                    stats["pay"] += 1
                    log.debug("dropped (pay $%s): %s [%s]", f"{pay_max:,}", title, board)
                    continue

                job = Job(
                    company=board, title=title, url=url,
                    location=(location if is_remote(location)
                              else f"{location} (Ashby workplace: {workplace or 'unknown'})"),
                    source="Ashby", posted_dt=parse_date(item.get("publishedAt")),
                    posted_label="Published", pay=pay or "Not listed", pay_max=pay_max,
                )

                if is_seen(raw_url, url, seen) or job.dedupe_key in batch_keys:
                    stats["seen"] += 1
                    continue

                if job.posted_dt and job.posted_dt < CUTOFF_DATE:
                    stats["old"] += 1
                    too_old.append(url)
                    continue

                batch_keys.add(job.dedupe_key)
                stats["kept"] += 1
                jobs.append(job)

        except HTTPError as ex:
            if ex.code == 404:
                log.warning("Ashby board '%s' not found (check the spelling in the URL).", board)
            else:
                log.error("Ashby %s failed: %s", board, ex)
            continue
        except Exception as ex:
            log.error("Ashby %s failed: %s", board, ex)
            continue

        log.info(
            "  %s (Ashby): %d open | %d title matches | %d not remote | %d low pay | "
            "%d already sent | %d older than %d days | %d listed",
            board, stats["total"], stats["title"], stats["not_remote"], stats["pay"],
            stats["seen"], stats["old"], DAYS_BACK, stats["kept"],
        )

    return jobs, too_old

# =====================================================
# LEVER
# =====================================================

LEVER_API = "https://api.lever.co/v0/postings"
LEVER_API_EU = "https://api.eu.lever.co/v0/postings"


def search_lever(seen: set[str], known_keys: set) -> tuple[list[Job], list[str]]:
    """Lever's public postings API returns a company's whole job list in one request."""
    jobs: list[Job] = []
    too_old: list[str] = []
    batch_keys = set(known_keys)

    for board in LEVER_BOARDS:
        stats: Counter = Counter()

        try:
            try:
                data = fetch_json(f"{LEVER_API}/{board}?mode=json")
            except HTTPError as ex:
                if ex.code != 404:
                    raise
                data = fetch_json(f"{LEVER_API_EU}/{board}?mode=json")  # EU-hosted boards

            for item in data if isinstance(data, list) else []:
                stats["total"] += 1

                title = text(item.get("text"))
                if not title_matches(title):
                    continue
                stats["title"] += 1

                raw_url = text(item.get("hostedUrl") or item.get("applyUrl"))
                if not raw_url:
                    continue
                url = normalize_url(raw_url)

                categories = item.get("categories") or {}
                places = [text(categories.get("location"))] + [
                    text(x) for x in (categories.get("allLocations") or [])
                ]
                location = "; ".join(dict.fromkeys(p for p in places if p)) or "Unknown"
                workplace = text(item.get("workplaceType")).lower()  # remote / hybrid / on-site / unspecified
                country = text(item.get("country"))

                remote = workplace == "remote" or (
                    workplace in ("", "unspecified") and is_remote(location)
                )
                wrong_country = (
                    country
                    and country.lower() not in US_COUNTRY_NAMES
                    and not any(re.search(p, location.lower()) for p in OK_REGION_PATTERNS)
                )

                if (
                    not remote
                    or looks_on_site(location)
                    or not remote_region_ok(location)
                    or wrong_country
                ):
                    stats["not_remote"] += 1
                    log.debug("dropped (not remote / non-US region): %s | %s %s",
                              title, location, workplace)
                    continue

                salary = item.get("salaryRange") or {}
                pay, pay_max = "Not listed", None
                interval = text(salary.get("interval")).lower()
                # turn hourly / weekly / monthly pay into a yearly figure so it can be judged
                per_year = (1 if "year" in interval else 2080 if "hour" in interval
                            else 52 if "week" in interval else 12 if "month" in interval else 0)
                if salary.get("currency") == "USD" and per_year:
                    lo = to_int(salary.get("min")) * per_year
                    hi = to_int(salary.get("max")) * per_year
                    if lo or hi:
                        pay, pay_max = f"${lo or hi:,} - ${hi or lo:,}", (hi or lo)

                if pay_max and pay_max < MIN_SALARY:
                    stats["pay"] += 1
                    log.debug("dropped (pay $%s): %s [%s]", f"{pay_max:,}", title, board)
                    continue

                job = Job(
                    company=board, title=title, url=url,
                    location=(location if is_remote(location)
                              else f"{location} (Lever workplace: {workplace or 'unknown'})"),
                    source="Lever", posted_dt=_ja_date(item.get("createdAt")),
                    pay=pay, pay_max=pay_max,
                )

                if is_seen(raw_url, url, seen) or job.dedupe_key in batch_keys:
                    stats["seen"] += 1
                    continue

                if job.posted_dt and job.posted_dt < CUTOFF_DATE:
                    stats["old"] += 1
                    too_old.append(url)
                    continue

                batch_keys.add(job.dedupe_key)
                stats["kept"] += 1
                jobs.append(job)

        except HTTPError as ex:
            if ex.code == 404:
                log.warning("Lever board '%s' not found (check the spelling in the URL).", board)
            else:
                log.error("Lever %s failed: %s", board, ex)
            continue
        except Exception as ex:
            log.error("Lever %s failed: %s", board, ex)
            continue

        log.info(
            "  %s (Lever): %d open | %d title matches | %d not remote | %d low pay | "
            "%d already sent | %d older than %d days | %d listed",
            board, stats["total"], stats["title"], stats["not_remote"], stats["pay"],
            stats["seen"], stats["old"], DAYS_BACK, stats["kept"],
        )

    return jobs, too_old


# =====================================================
# REMOTE JOB BOARDS
# =====================================================

def fetch_remotive() -> Iterator[Job]:
    data = fetch_json("https://remotive.com/api/remote-jobs")

    for j in data.get("jobs", []):
        salary = text(j.get("salary"))
        yield Job(
            company=text(j.get("company_name")),
            title=text(j.get("title")),
            url=text(j.get("url")),
            location=text(j.get("candidate_required_location")),
            source="Remotive",
            posted_dt=parse_date(j.get("publication_date")),
            pay=salary or "Not listed",
            pay_max=max(parse_amounts(salary), default=None),
        )


def fetch_remoteok() -> Iterator[Job]:
    for j in fetch_json("https://remoteok.com/api"):
        if not isinstance(j, dict) or "position" not in j:
            continue  # first item is a legal notice

        url = text(j.get("url") or j.get("apply_url"))
        if url.startswith("/"):
            url = "https://remoteok.com" + url

        lo, hi = to_int(j.get("salary_min")), to_int(j.get("salary_max"))
        yield Job(
            company=text(j.get("company")),
            title=text(j.get("position")),
            url=url,
            location=text(j.get("location")),
            source="Remote OK",
            posted_dt=parse_date(j.get("date")),
            pay=f"${lo:,} - ${hi:,}" if (lo or hi) else "Not listed",
            pay_max=(hi or lo) or None,
        )


def fetch_weworkremotely() -> Iterator[Job]:
    root = ET.fromstring(http_get("https://weworkremotely.com/remote-jobs.rss", timeout=30))

    for item in root.iter("item"):
        raw_title = text(item.findtext("title"))
        company, sep, title = raw_title.partition(": ")
        if not sep:
            company, title = "", raw_title

        try:
            posted_dt = parsedate_to_datetime(item.findtext("pubDate"))
            if posted_dt.tzinfo is None:
                posted_dt = posted_dt.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            posted_dt = None

        yield Job(
            company=company,
            title=title,
            url=text(item.findtext("link")),
            location=text(item.findtext("region")),
            source="We Work Remotely",
            posted_dt=posted_dt,
        )


# ----- Jobright (your own export; nothing is fetched from jobright.ai) -----

def _load_json_documents(raw: str) -> list:
    """Parse one JSON document, or several pasted one after another."""
    decoder = json.JSONDecoder()
    docs, i, raw = [], 0, raw.strip()
    while i < len(raw):
        try:
            doc, end = decoder.raw_decode(raw, i)
        except ValueError:
            nxt = [q for q in (raw.find("{", i + 1), raw.find("[", i + 1)) if q != -1]
            if not nxt:
                break
            i = min(nxt)
            continue
        docs.append(doc)
        i = end
        while i < len(raw) and raw[i].isspace():
            i += 1
    return docs


def _jobright_items(node):
    """Yield (job_dict, company_dict) for every job found in the export."""
    if isinstance(node, dict):
        if isinstance(node.get("jobResult"), dict):
            yield node["jobResult"], node.get("companyResult") or {}
            return
        if "jobTitle" in node and ("applyLink" in node or "originalUrl" in node):
            yield node, {}
            return
        for value in node.values():
            yield from _jobright_items(value)
    elif isinstance(node, list):
        for value in node:
            yield from _jobright_items(value)


def fetch_jobright_file() -> Iterator[Job]:
    age_days = (time.time() - JOBRIGHT_FILE.stat().st_mtime) / 86400
    if age_days > JOBRIGHT_STALE_DAYS:
        log.warning("%s is %.0f days old: export a fresh response for new jobs.",
                    JOBRIGHT_FILE.name, age_days)

    raw = JOBRIGHT_FILE.read_text(encoding="utf-8", errors="replace")
    done = set()

    for doc in _load_json_documents(raw):
        for jr, company in _jobright_items(doc):
            key = text(jr.get("jobId")) or text(jr.get("applyLink"))
            if key in done:
                continue
            done.add(key)

            title = text(jr.get("jobTitle"))
            if jr.get("isDeleted") or jr.get("isClearanceRequired") or jr.get("isCitizenOnly"):
                log.debug("dropped (Jobright: deleted / clearance / citizen-only): %s", title)
                continue

            url = text(jr.get("applyLink") or jr.get("originalUrl"))
            where = text(jr.get("jobLocation")) or ", ".join(jr.get("jobLocations") or [])
            model = text(jr.get("workModel")).lower()

            if re.search(r"hybrid|on[-_]?site", url, re.I):
                location = f"Hybrid/on-site per link: {where}"
            elif model == "remote":
                location = f"Remote - {where}" if where else "Remote"
            else:
                location = f"{model.title() or 'Unknown'}: {where}"

            pay_text = text(jr.get("salaryDesc") or jr.get("salary"))
            yield Job(
                company=text(company.get("companyName") or jr.get("companyName")),
                title=title,
                url=url,
                location=location,
                source="Jobright",
                posted_dt=parse_date(jr.get("publishTime")),
                pay=pay_text or "Not listed",
                pay_max=max(parse_amounts(pay_text), default=None),
            )


# ----- JobAssist (your own export; nothing is fetched from jobassist.com) -----

_JA_TITLE = ("jobTitle", "title", "job_title", "positionName", "position", "jobName")
_JA_URL = ("applyUrl", "applyLink", "apply_url", "jobUrl", "jobLink", "originalUrl",
           "sourceUrl", "externalUrl", "absolute_url", "url", "link")
_JA_COMPANY = ("companyName", "company_name", "employerName", "employer", "company", "organization")
_JA_WHERE = ("location", "jobLocation", "locations", "candidateLocation", "city", "region")
_JA_COUNTRY = ("country", "countryCode", "country_code")
_JA_MODEL = ("workType", "workModel", "workplaceType", "locationType", "remoteType", "workMode")
_JA_DATE = ("postedAt", "publishedAt", "publishTime", "datePosted", "postedDate", "createdAt",
            "posted_at", "published_at", "postingDate", "date")
_JA_SAL_MIN = ("salaryMin", "minSalary", "salary_min", "min_salary", "salaryFrom")
_JA_SAL_MAX = ("salaryMax", "maxSalary", "salary_max", "max_salary", "salaryTo")

# extra spellings used by TheirStack records
_JA_URL = ("final_url",) + _JA_URL + ("source_url",)
_JA_COMPANY = _JA_COMPANY + ("company_object",)
_JA_WHERE = _JA_WHERE + ("short_location", "long_location")
_JA_DATE = _JA_DATE + ("date_posted", "discovered_at")
_JA_SAL_MIN = _JA_SAL_MIN + ("min_annual_salary_usd",)
_JA_SAL_MAX = _JA_SAL_MAX + ("max_annual_salary_usd",)

# extra spellings used by Workable records
_JA_MODEL = _JA_MODEL + ("workplace", "workplace_type")
_JA_DATE = _JA_DATE + ("published_on", "created_at", "created")


def _pick(record: dict, keys):
    for key in keys:
        value = record.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _ja_text(value) -> str:
    if isinstance(value, dict):
        for key in ("name", "label", "display", "formatted", "location_str",
                    "fullLocation", "full_location", "title"):
            if value.get(key):
                return text(value[key])
        parts = [text(value.get(k)) for k in
                 ("city", "region", "state", "country", "countryName", "country_name",
                  "countryCode", "country_code") if value.get(k)]
        return ", ".join(dict.fromkeys(parts))
    if isinstance(value, list):
        return "; ".join(t for t in (_ja_text(v) for v in value) if t)
    return text(value)


def _ja_date(value) -> Optional[datetime]:
    if isinstance(value, (int, float)) or text(value).isdigit():
        n = float(value)
        n = n / 1000 if n > 1e11 else n  # milliseconds -> seconds
        try:
            return datetime.fromtimestamp(n, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    return parse_date(value)


def _ja_records(node):
    """Yield every dict that looks like a job: a title plus an http(s) link."""
    if isinstance(node, dict):
        title, url = _pick(node, _JA_TITLE), _pick(node, _JA_URL)
        if isinstance(title, str) and isinstance(url, str) and url.startswith("http"):
            yield node
            return
        for value in node.values():
            yield from _ja_records(value)
    elif isinstance(node, list):
        for value in node:
            yield from _ja_records(value)


def _ja_location(rec: dict, where: str, assume_remote=None) -> str:
    if assume_remote is None:
        assume_remote = JOBASSIST_ASSUME_REMOTE
    nested = rec.get("location") if isinstance(rec.get("location"), dict) else {}
    model = (_ja_text(_pick(rec, _JA_MODEL)) + " " + text(nested.get("workplace_type"))).lower()
    flag = rec["isRemote"] if "isRemote" in rec else rec.get("remote")
    if flag is None:
        flag = rec.get("telecommuting", nested.get("telecommuting"))

    if rec.get("hybrid") is True or re.search(r"hybrid|on[-_ ]?site|in[-_ ]?office|office", model):
        return f"Hybrid/on-site: {where}"
    if "remote" in model or flag is True:
        return where if where.lower().startswith("remote") else (f"Remote - {where}" if where else "Remote")
    if flag is False:
        return f"On-site: {where}"
    if assume_remote:
        return where if where.lower().startswith("remote") else (f"Remote - {where}" if where else "Remote")
    return f"On-site (no remote flag): {where}"


def _ja_job(rec: dict, url: str, source: str, assume_remote=None) -> Job:
    """Turn one export / API record into a Job (shared by JobAssist and TheirStack)."""
    where = _ja_text(_pick(rec, _JA_WHERE))
    country = _ja_text(_pick(rec, _JA_COUNTRY))
    if country and country.lower() not in where.lower():
        where = f"{where}, {country}" if where else country
    lo = to_int(_pick(rec, _JA_SAL_MIN))
    hi = to_int(_pick(rec, _JA_SAL_MAX))
    unit = text(rec.get("salaryUnit") or rec.get("salary_unit")).lower()
    if (unit and not re.search(r"year|annual", unit)) or max(lo, hi) < 1000:
        lo = hi = 0  # hourly or unknown unit: do not judge pay

    return Job(
        company=_ja_text(_pick(rec, _JA_COMPANY)),
        title=text(_pick(rec, _JA_TITLE)),
        url=url,
        location=_ja_location(rec, where, assume_remote),
        source=source,
        posted_dt=_ja_date(_pick(rec, _JA_DATE)),
        pay=f"${lo or hi:,} - ${hi or lo:,}" if (lo or hi) else "Not listed",
        pay_max=(hi or lo) or None,
    )


def fetch_jobassist_file() -> Iterator[Job]:
    age_days = (time.time() - JOBASSIST_FILE.stat().st_mtime) / 86400
    if age_days > JOBASSIST_STALE_DAYS:
        log.warning("%s is %.0f days old: export a fresh response for new jobs.",
                    JOBASSIST_FILE.name, age_days)

    raw = JOBASSIST_FILE.read_text(encoding="utf-8", errors="replace")
    done, found = set(), 0

    for doc in _load_json_documents(raw):
        for rec in _ja_records(doc):
            url = text(_pick(rec, _JA_URL))
            if url in done:
                continue
            done.add(url)
            found += 1

            yield _ja_job(rec, url, "JobAssist")

    if found == 0:
        log.warning("  JobAssist: %s was read but no job records were recognised. "
                    "Paste ONE job entry (with personal details removed) so the importer "
                    "can be adjusted.", JOBASSIST_FILE.name)
    else:
        log.info("  JobAssist: %d job records recognised in %s", found, JOBASSIST_FILE.name)


# ----- TheirStack (public API; the free plan has a small monthly credit allowance) -----

THEIRSTACK_URL = "https://api.theirstack.com/v1/jobs/search"


def _month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _theirstack_state() -> dict:
    try:
        data = json.loads(THEIRSTACK_USAGE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    if data.get("month") != _month_key():
        data["month"], data["used"] = _month_key(), 0  # credits reset monthly
    data.setdefault("used", 0)
    data.setdefault("ids", [])  # job IDs already paid for, so they are never fetched again
    return data


def _theirstack_used() -> int:
    return int(_theirstack_state()["used"])


def _theirstack_add_usage(records: list) -> None:
    state = _theirstack_state()
    state["used"] += len(records)
    state["ids"] = (state["ids"] + [r["id"] for r in records if isinstance(r.get("id"), int)])[-400:]
    try:
        THEIRSTACK_USAGE_FILE.write_text(json.dumps(state), encoding="utf-8")
    except OSError as ex:
        log.warning("Could not record TheirStack credit use: %s", ex)


def _theirstack_cached():
    try:
        if time.time() - THEIRSTACK_CACHE_FILE.stat().st_mtime < THEIRSTACK_CACHE_HOURS * 3600:
            return json.loads(THEIRSTACK_CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return None


def fetch_theirstack() -> Iterator[Job]:
    records = _theirstack_cached()

    if records is not None:
        log.info("  TheirStack: reusing results saved in the last %d hours (no credits used)",
                 THEIRSTACK_CACHE_HOURS)
    else:
        left = THEIRSTACK_MONTHLY_BUDGET - _theirstack_used()
        limit = min(THEIRSTACK_MAX_JOBS_PER_RUN, left)
        if limit <= 0:
            log.info("  TheirStack: skipped, the monthly budget of %d credits is used up.",
                     THEIRSTACK_MONTHLY_BUDGET)
            return

        titles = sorted({
            k for k in TITLE_KEYWORDS
            if INCLUDE_SOLUTIONS_ENGINEERS or not _SOLUTIONS_RE.search(k)
        })
        body = {
            "job_title_or": titles,
            "job_title_not": ["intern", "internship", "director", "sales", "representative"],
            "job_country_code_or": ["US"],
            "workplace_types_or": ["remote"],
            "posted_at_max_age_days": max(1, min(THEIRSTACK_MAX_AGE_DAYS, DAYS_BACK)),
            "limit": limit,
            "order_by": [{"field": "date_posted", "desc": True}],
        }
        if THEIRSTACK_DIRECT_EMPLOYERS_ONLY:
            body["company_type"] = "direct_employer"

        paid_ids = _theirstack_state()["ids"]
        if paid_ids:
            body["job_id_not"] = paid_ids  # never pay for the same job twice

        request = Request(
            THEIRSTACK_URL,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {os.environ.get('THEIRSTACK_API_KEY', '').strip()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urlopen(request, timeout=60) as response:
                payload = json.loads(response.read())
        except HTTPError as ex:
            reasons = {401: "the API key was rejected", 402: "out of credits",
                       403: "access denied", 429: "rate limited, try later"}
            try:
                detail = ex.read().decode("utf-8", "replace").strip()[:300]
            except Exception:
                detail = ""
            log.error("  TheirStack request failed: HTTP %s (%s) %s",
                      ex.code, reasons.get(ex.code, ex.reason), detail)
            return

        records = payload.get("data", []) if isinstance(payload, dict) else payload
        records = [r for r in records if isinstance(r, dict)]
        _theirstack_add_usage(records)
        try:
            THEIRSTACK_CACHE_FILE.write_text(json.dumps(records), encoding="utf-8")
        except OSError:
            pass
        log.info("  TheirStack: %d jobs returned, about %d of %d monthly credits used",
                 len(records), _theirstack_used(), THEIRSTACK_MONTHLY_BUDGET)

    done = set()
    for rec in records:
        url = text(_pick(rec, _JA_URL))
        if not url or url in done:
            continue
        done.add(url)
        yield _ja_job(rec, url, "TheirStack")


# ----- Workable (public company job feeds + Workable's own job search) -----

WORKABLE_WIDGET = "https://apply.workable.com/api/v1/widget/accounts"
WORKABLE_SEARCH = "https://jobs.workable.com/api/v1/jobs"


def fetch_workable_search() -> Iterator[Job]:
    """Keyword search across every company that uses Workable (remote, US)."""
    done: set[str] = set()
    seen_keys: list[str] = []

    for query in WORKABLE_SEARCH_QUERIES:
        token = ""
        for _page in range(WORKABLE_SEARCH_PAGES):
            params = {"query": query, "workplace": "remote", "location": "United States"}
            if token:
                params["pageToken"] = token
            data = fetch_json(f"{WORKABLE_SEARCH}?{urlencode(params)}")
            if isinstance(data, dict) and not seen_keys:
                seen_keys = list(data.keys())[:10]

            records = list(_ja_records(data))
            for rec in records:
                url = text(_pick(rec, _JA_URL))
                if url in done:
                    continue
                done.add(url)
                yield _ja_job(rec, url, "Workable", assume_remote=True)

            token = text(data.get("nextPageToken")) if isinstance(data, dict) else ""
            if not token or not records:
                break
            time.sleep(0.3)
        time.sleep(0.3)

    if not done:
        log.warning("  Workable search: no job records were recognised (response keys: %s). "
                    "Paste ONE job entry from the response so the importer can be adjusted.",
                    seen_keys or "none")


def search_workable(seen: set[str], known_keys: set) -> tuple[list[Job], list[str]]:
    """Specific companies on Workable (apply.workable.com/<name>)."""
    from dataclasses import replace

    jobs: list[Job] = []
    too_old: list[str] = []
    batch_keys = set(known_keys)

    for board in WORKABLE_BOARDS:
        stats: Counter = Counter()
        try:
            data = fetch_json(f"{WORKABLE_WIDGET}/{board}")
            for item in (data.get("jobs") or []) if isinstance(data, dict) else []:
                stats["total"] += 1
                title = text(item.get("title"))
                if not title_matches(title):
                    continue
                stats["title"] += 1

                raw_url = text(item.get("url") or item.get("shortlink"))
                if not raw_url:
                    continue
                job = replace(
                    _ja_job(item, normalize_url(raw_url), "Workable", assume_remote=False),
                    company=board,
                )

                if (not is_remote(job.location) or looks_on_site(job.location)
                        or not remote_region_ok(job.location)):
                    stats["not_remote"] += 1
                    log.debug("dropped (not remote / non-US region): %s | %s", title, job.location)
                    continue
                if job.pay_max and job.pay_max < MIN_SALARY:
                    stats["pay"] += 1
                    continue
                if is_seen(raw_url, job.url, seen) or job.dedupe_key in batch_keys:
                    stats["seen"] += 1
                    continue
                if job.posted_dt and job.posted_dt < CUTOFF_DATE:
                    stats["old"] += 1
                    too_old.append(job.url)
                    continue

                batch_keys.add(job.dedupe_key)
                stats["kept"] += 1
                jobs.append(job)

        except HTTPError as ex:
            if ex.code == 404:
                log.warning("Workable board '%s' not found (check the name in apply.workable.com/<name>).", board)
            else:
                log.error("Workable %s failed: %s", board, ex)
            continue
        except Exception as ex:
            log.error("Workable %s failed: %s", board, ex)
            continue

        log.info(
            "  %s (Workable): %d open | %d title matches | %d not remote | %d low pay | "
            "%d already sent | %d older than %d days | %d listed",
            board, stats["total"], stats["title"], stats["not_remote"], stats["pay"],
            stats["seen"], stats["old"], DAYS_BACK, stats["kept"],
        )

    return jobs, too_old


def search_remote_boards(seen: set[str], known_keys: set) -> tuple[list[Job], list[str]]:
    sources: list[tuple[str, Callable[[], Iterator[Job]]]] = []
    if USE_REMOTIVE:
        sources.append(("Remotive", fetch_remotive))
    if USE_REMOTEOK:
        sources.append(("Remote OK", fetch_remoteok))
    if USE_WEWORKREMOTELY:
        sources.append(("We Work Remotely", fetch_weworkremotely))
    if USE_WORKABLE_SEARCH:
        sources.append(("Workable (search)", fetch_workable_search))
    if USE_THEIRSTACK and os.environ.get("THEIRSTACK_API_KEY", "").strip():
        sources.append(("TheirStack (API)", fetch_theirstack))
    elif USE_THEIRSTACK:
        log.info("  TheirStack: skipped, set THEIRSTACK_API_KEY to use it (free signup at theirstack.com)")
    if USE_JOBASSIST_FILE and JOBASSIST_FILE.exists():
        sources.append(("JobAssist (your export)", fetch_jobassist_file))
    elif USE_JOBASSIST_FILE:
        log.info("  JobAssist: skipped, no export found. To use it, save your JobAssist "
                 "jobs response as this file: %s", JOBASSIST_FILE)
    if USE_JOBRIGHT_FILE and JOBRIGHT_FILE.exists():
        sources.append(("Jobright (your export)", fetch_jobright_file))
    elif USE_JOBRIGHT_FILE:
        log.info("  Jobright: skipped, no export found. To use it, save your Jobright "
                 "response as this file: %s", JOBRIGHT_FILE)

    found: list[Job] = []
    too_old: list[str] = []
    batch_keys = set(known_keys)  # includes Greenhouse results, to dedupe across sources

    for label, fetcher in sources:
        stats: Counter = Counter()

        try:
            for job in fetcher():
                stats["total"] += 1

                if not title_matches(job.title):
                    continue
                stats["title"] += 1

                if not job.url:
                    continue
                raw_url = job.url
                job.url = normalize_url(raw_url)

                if looks_on_site(f"{job.location} {job.title}") or not region_ok(job.location):
                    stats["region"] += 1
                    log.debug("dropped (region): %s | %s [%s]",
                              job.title, job.location or "no region", job.company)
                    continue

                if job.pay_max and job.pay_max < MIN_SALARY:
                    stats["pay"] += 1
                    log.debug("dropped (pay $%s): %s [%s]", f"{job.pay_max:,}", job.title, job.company)
                    continue

                if is_seen(raw_url, job.url, seen) or job.dedupe_key in batch_keys:
                    stats["seen"] += 1
                    continue

                if job.posted_dt and job.posted_dt < CUTOFF_DATE:
                    stats["old"] += 1
                    too_old.append(job.url)
                    continue

                job.location = job.location or "Remote"
                batch_keys.add(job.dedupe_key)
                stats["kept"] += 1
                found.append(job)

        except Exception as ex:
            log.error("%s failed: %s", label, ex)
            continue

        log.info(
            "  %s: %d jobs | %d title matches | %d wrong region/not remote | %d low pay | "
            "%d already sent | %d older than %d days | %d listed",
            label, stats["total"], stats["title"], stats["region"], stats["pay"],
            stats["seen"], stats["old"], DAYS_BACK, stats["kept"],
        )

    return found, too_old

# =====================================================
# SEARCH LINKS
# =====================================================

def build_google_url() -> str:
    # Google Jobs understands "after:YYYY-MM-DD"
    return (
        "https://www.google.com/search?udm=jobs"
        "&q=remote%20("
        "%22support%20engineer%22%20OR%20"
        "%22technical%20support%20engineer%22%20OR%20"
        "%22application%20support%22%20OR%20"
        "%22solutions%20engineer%22%20OR%20"
        "%22technical%20account%20manager%22"
        ")%20jobs%20Full%20time%20remote%20Full%20time"
        f"%20after%3A{CUTOFF_DATE:%Y-%m-%d}"
    )


def build_jobassist_url() -> str:
    # JobAssist is an account-based app with no public job feed, so this is a
    # click-through lead only (like Google, Indeed and LinkedIn). Filters are the
    # ones from your own JobAssist search; the salary floor follows MIN_SALARY.
    return (
        "https://jobassist.com/explore?workType=remote&workArrangement=full-time"
        f"&minSalary={MIN_SALARY}&salaryUnit=annually&industriesAny=1&sortBy=newest"
        "&exactTitles=technical+support+engineer%2CProduct+support+engineer"
        "%2CTechnical+support+specialist%2CCustomer+support+specialist"
        "&search=technical+support+engineer"
    )


def build_indeed_url() -> str:
    url = (
        "https://www.indeed.com/jobs?q=%22support+engineer%22&l=remote"
        "&salaryType=%2490%2C000%2B&forceLocation=1"
        "&sc=0kf%3Aattr%28CF3CP%29attr%28DSQF7%29%3B&from=searchOnDesktopSerp"
    )
    # Indeed only accepts 1, 3, 7 or 14 days. Use the smallest option that is at
    # least as wide as DAYS_BACK; for longer windows (e.g. 41) add no filter.
    for allowed in (1, 3, 7, 14):
        if allowed >= DAYS_BACK:
            return url + f"&fromage={allowed}"
    return url


def build_linkedin_url() -> str:
    # LinkedIn blocks automated scraping and needs a login, so this is a
    # click-through lead only (like Google and Indeed), not a searched source.
    # The original link's currentJobId (pins one specific job) and origin
    # (tracking) params are intentionally left out.
    return (
        "https://www.linkedin.com/jobs/search-results/"
        "?keywords=application%20support%20engineer%20Full-time%20%2498%2C000%2B"
        "%20Remote%20posted%20in%20the%20past%20week"
    )


# =====================================================
# EMAIL
# =====================================================

ATTRIBUTION = ("Job data from Greenhouse, Lever, Workable, Ashby, Remotive (remotive.com), Remote OK (remoteok.com), "
               "We Work Remotely (weworkremotely.com), TheirStack (theirstack.com) and your own "
               "Jobright / JobAssist exports.")


def build_plain(jobs: list[Job], google_url: str, indeed_url: str, linkedin_url: str) -> str:
    lines = [
        "", "DAILY REMOTE JOB REPORT", "=" * 60, "",
        f"Search window: last {DAYS_BACK} days (since {CUTOFF_DATE:%Y-%m-%d})", "",
        "JOB SEARCH LEADS", "-" * 60,
        f"Google Search:\n{google_url}", "",
        f"Indeed Search:\n{indeed_url}", "",
        f"LinkedIn Search:\n{linkedin_url}", "",
        f"JobAssist Search:\n{build_jobassist_url()}", "",
        f"Jobright (your saved filters):\n{JOBRIGHT_URL}", "",
        "=" * 60, "",
    ]

    if jobs:
        for idx, job in enumerate(jobs, start=1):
            lines += [
                f"{idx}. {job.title}",
                f"Company: {job.company}",
                f"Location: {job.location}",
                f"Source: {job.source}",
                job.posted,
                f"Salary: {job.pay} ({salary_indicator(job.pay_max)})",
                f"Apply: {job.url}",
                "-" * 60, "",
            ]
    else:
        lines += [f"No new remote jobs from the last {DAYS_BACK} days.", ""]

    lines += ["=" * 60, f"New Remote Jobs: {len(jobs)}", "", ATTRIBUTION]
    return "\n".join(lines)


def build_html(jobs: list[Job], google_url: str, indeed_url: str, linkedin_url: str) -> str:
    e = html.escape

    cards = []
    for job in jobs:
        cards.append(
            '<div style="border:1px solid #ddd;border-radius:8px;padding:12px;margin:0 0 12px">'
            f'<div style="font-size:16px;font-weight:600">'
            f'<a href="{e(job.url, quote=True)}" style="color:#1a56db;text-decoration:none">{e(job.title)}</a></div>'
            f'<div>{e(job.company)} &middot; {e(job.location)}</div>'
            f'<div style="color:#555;font-size:13px">{e(job.source)} · {e(job.posted)} · Salary: {e(job.pay)} ({salary_indicator(job.pay_max)})</div>'
            "</div>"
        )
    if not cards:
        cards.append(f"<p>No new remote jobs from the last {DAYS_BACK} days.</p>")

    return (
        '<html><body style="font-family:Arial,sans-serif;max-width:640px;margin:auto">'
        "<h2>Daily Remote Job Report</h2>"
        f"<p>Search window: last {DAYS_BACK} days (since {CUTOFF_DATE:%Y-%m-%d})</p>"
        f'<p><a href="{e(google_url, quote=True)}">Google Jobs search</a> &middot; '
        f'<a href="{e(indeed_url, quote=True)}">Indeed search</a> &middot; '
        f'<a href="{e(linkedin_url, quote=True)}">LinkedIn search</a> &middot; '
        f'<a href="{e(build_jobassist_url(), quote=True)}">JobAssist search</a> &middot; '
        f'<a href="{e(JOBRIGHT_URL, quote=True)}">Jobright</a></p>'
        f"<h3>New Remote Jobs: {len(jobs)}</h3>"
        + "".join(cards)
        + f'<p style="color:#888;font-size:12px">{e(ATTRIBUTION)}</p></body></html>'
    )


def load_email_config() -> Optional[EmailConfig]:
    sender = os.environ.get("JOB_ALERT_EMAIL_FROM", "").strip() or DEFAULT_EMAIL_FROM
    password = os.environ.get("JOB_ALERT_EMAIL_PASSWORD", "")
    recipients = [
        a.strip() for a in os.environ.get("JOB_ALERT_EMAIL_TO", "").split(",") if a.strip()
    ] or DEFAULT_EMAIL_TO or ([sender] if sender else [])

    missing = [
        name for name, value in (
            ("JOB_ALERT_EMAIL_FROM", sender),
            ("JOB_ALERT_EMAIL_PASSWORD", password),
        ) if not value
    ]
    if missing:
        log.error("Missing environment variable(s): %s", ", ".join(missing))
        return None

    return EmailConfig(sender, recipients, password)


def send_email(cfg: EmailConfig, subject: str, plain: str, html_body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg.sender
    msg["To"] = ", ".join(cfg.recipients)
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(cfg.sender, cfg.password)
        server.sendmail(cfg.sender, cfg.recipients, msg.as_string())


# =====================================================
# SAVING RESULTS
# =====================================================

DEFAULT_CSV_FIELDS = [
    "company", "title", "url", "location", "source", "posted", "pay", "date_found",
]


def append_csv(jobs: list[Job]) -> None:
    fieldnames = DEFAULT_CSV_FIELDS

    # If a CSV from an older version exists, keep writing with ITS columns
    # so rows stay aligned.
    if CSV_FILE.exists():
        with open(CSV_FILE, "r", newline="", encoding="utf-8") as f:
            header = next(csv.reader(f), None)
        if header:
            fieldnames = header

    write_header = not CSV_FILE.exists() or CSV_FILE.stat().st_size == 0

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore", restval="")
        if write_header:
            writer.writeheader()
        writer.writerows(job.as_row() for job in jobs)


# =====================================================
# MAIN
# =====================================================

def setup_logging(verbose: bool) -> None:
    log.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(fmt)

    logfile = RotatingFileHandler(LOG_FILE, maxBytes=500_000, backupCount=3, encoding="utf-8")
    logfile.setLevel(logging.DEBUG)  # the file always gets the "dropped ..." detail
    logfile.setFormatter(fmt)

    log.addHandler(console)
    log.addHandler(logfile)


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily remote job alert")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the email instead of sending; save nothing")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="show per-job 'dropped' lines on the console")
    args = parser.parse_args()

    setup_logging(args.verbose)

    cfg = None
    if not args.dry_run:
        cfg = load_email_config()
        if cfg is None:
            log.error("Nothing was searched or saved.")
            return 1

    seen = load_seen() | keys_from_csv()

    jobs: list[Job] = []
    too_old: list[str] = []

    if COMPANIES:
        log.info("Searching Greenhouse for remote jobs from the last %d days...", DAYS_BACK)
        gh_jobs, gh_old = search_greenhouse(seen)
        jobs += gh_jobs
        too_old += gh_old

    if ASHBY_BOARDS:
        log.info("Searching Ashby boards for remote jobs from the last %d days...", DAYS_BACK)
        ashby_jobs, ashby_old = search_ashby(seen, {j.dedupe_key for j in jobs})
        jobs += ashby_jobs
        too_old += ashby_old

    if LEVER_BOARDS:
        log.info("Searching Lever boards for remote jobs from the last %d days...", DAYS_BACK)
        lever_jobs, lever_old = search_lever(seen, {j.dedupe_key for j in jobs})
        jobs += lever_jobs
        too_old += lever_old

    if WORKABLE_BOARDS:
        log.info("Searching Workable boards for remote jobs from the last %d days...", DAYS_BACK)
        workable_jobs, workable_old = search_workable(seen, {j.dedupe_key for j in jobs})
        jobs += workable_jobs
        too_old += workable_old

    log.info("Searching remote job boards by keyword (last %d days)...", DAYS_BACK)
    board_jobs, board_old = search_remote_boards(seen, {j.dedupe_key for j in jobs})
    jobs += board_jobs
    too_old += board_old

    sort_newest(jobs)

    # The same job often arrives from two sources with different links (for example your
    # Jobright export and the company's own Greenhouse board). Skip ones already emailed.
    before = len(jobs)
    jobs = [j for j in jobs if seen_key(j) not in seen]
    if len(jobs) < before:
        log.info("Skipped %d job(s) already emailed earlier from another source.", before - len(jobs))
    log.info("Found %d new remote jobs.", len(jobs))

    google_url, indeed_url = build_google_url(), build_indeed_url()
    linkedin_url = build_linkedin_url()
    plain = build_plain(jobs, google_url, indeed_url, linkedin_url)

    if args.dry_run:
        print(plain)
        log.info("Dry run: nothing sent or saved.")
        return 0

    # Old jobs never get newer, so remember them and stop re-checking.
    try:
        save_seen(too_old, seen)
    except OSError as ex:
        log.error("Could not update %s: %s", SEEN_FILE.name, ex)

    subject = f"Remote Job Alert - {len(jobs)} New Jobs - Last {DAYS_BACK} Days"

    try:
        send_email(cfg, subject, plain, build_html(jobs, google_url, indeed_url, linkedin_url))
    except Exception as ex:
        log.error("Email failed: %s", ex)
        log.error("Nothing was saved, so these jobs will show up next time.")
        return 1

    log.info("Email sent successfully (%d new jobs).", len(jobs))
    print(
        "✅ Email sent successfully."
    )

    print(
        f"✅ {len(jobs)} new jobs found."
    )

    # The email is out, so record it. Seen-list first: it prevents duplicate
    # emails. Each step has its own handler so one failure cannot hide the other.
    exit_code = 0

    try:
        save_seen([j.url for j in jobs], seen)
    except OSError as ex:
        log.error("Email sent, but could not update %s (these jobs may be re-sent): %s",
                  SEEN_FILE.name, ex)
        exit_code = 1

    if jobs:
        try:
            append_csv(jobs)
        except OSError as ex:
            log.error("Email sent, but could not write %s (is it open in Excel?): %s",
                      CSV_FILE.name, ex)
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
