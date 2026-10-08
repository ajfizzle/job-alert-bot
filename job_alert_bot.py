#!/usr/bin/env python3
"""Simple job search script for quickly finding matching remote jobs."""

from __future__ import annotations

import argparse
import json
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

DEFAULT_API_URL = "https://remotive.com/api/remote-jobs"


def fetch_jobs(api_url: str, timeout: int = 10) -> list[dict[str, Any]]:
    """Fetch jobs from the API endpoint and return the jobs list."""
    with urlopen(api_url, timeout=timeout) as response:  # nosec B310
        payload = json.load(response)
    jobs = payload.get("jobs")
    return jobs if isinstance(jobs, list) else []


def _job_text(job: dict[str, Any]) -> str:
    parts = [
        str(job.get("title", "")),
        str(job.get("company_name", "")),
        str(job.get("category", "")),
        str(job.get("candidate_required_location", "")),
        str(job.get("description", "")),
        str(job.get("tags", "")),
    ]
    return " ".join(parts).lower()


def filter_jobs(
    jobs: list[dict[str, Any]],
    keywords: list[str] | None = None,
    location: str | None = None,
) -> list[dict[str, Any]]:
    """Filter jobs by keyword(s) and candidate location text."""
    normalized_keywords = [keyword.lower() for keyword in (keywords or []) if keyword.strip()]
    normalized_location = location.lower() if location else None

    filtered: list[dict[str, Any]] = []
    for job in jobs:
        searchable_text = _job_text(job)

        if normalized_keywords and not any(keyword in searchable_text for keyword in normalized_keywords):
            continue

        if normalized_location:
            candidate_location = str(job.get("candidate_required_location", "")).lower()
            if normalized_location not in candidate_location:
                continue

        filtered.append(job)

    return filtered


def format_job(job: dict[str, Any]) -> str:
    """Format a single job for terminal output."""
    title = job.get("title", "Unknown title")
    company = job.get("company_name", "Unknown company")
    location = job.get("candidate_required_location", "Unknown location")
    url = job.get("url", "No URL provided")
    return f"- {title} at {company} ({location})\n  {url}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Find remote jobs by keyword and location.")
    parser.add_argument(
        "--keyword",
        action="append",
        default=[],
        help="Keyword to match (can be repeated, e.g. --keyword python --keyword django)",
    )
    parser.add_argument("--location", help="Filter by candidate location text, e.g. 'Worldwide' or 'US'.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of results to print (default: 10).")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Jobs API URL (default: Remotive API).")
    parser.add_argument("--timeout", type=int, default=10, help="HTTP timeout in seconds (default: 10).")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        jobs = fetch_jobs(args.api_url, timeout=args.timeout)
    except URLError as exc:
        print(f"Failed to fetch jobs: {exc}")
        return 1

    matched_jobs = filter_jobs(jobs, keywords=args.keyword, location=args.location)

    if not matched_jobs:
        print("No matching jobs found.")
        return 0

    for job in matched_jobs[: max(args.limit, 0)]:
        print(format_job(job))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
