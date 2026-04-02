"""
Indeed searcher — scrapes Indeed job listings via their public RSS feed.
RSS endpoint: https://www.indeed.com/rss?q={query}&l={location}&sort=date&fromage={days}
"""

import time
import urllib.parse
from datetime import datetime, timezone

import feedparser
import requests
from bs4 import BeautifulSoup

from src.config import SEARCH_DAYS_BACK
from src.resume_parser import CandidateProfile
from src.searchers.base import JobListing, JobSearcher

_RSS_URL = (
    "https://www.indeed.com/rss"
    "?q={query}&l=United+States&sort=date&fromage={days}&limit=50"
)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _build_indeed_query(profile: CandidateProfile) -> list[str]:
    """Build multiple Indeed search queries from the candidate profile."""
    queries = []
    # One query per target role (avoid one giant boolean query)
    for role in profile.target_roles[:4]:  # limit to 4 roles
        queries.append(role)
    # Add a keywords-based query
    top_kws = " OR ".join(f'"{kw}"' for kw in profile.search_keywords[:5])
    if top_kws:
        queries.append(top_kws)
    return queries


class IndeedSearcher(JobSearcher):
    name = "Indeed"

    def search(self, profile: CandidateProfile) -> list[JobListing]:
        results: list[JobListing] = []
        seen_urls: set[str] = set()
        queries = _build_indeed_query(profile)

        for query in queries:
            encoded_query = urllib.parse.quote_plus(query)
            url = _RSS_URL.format(query=encoded_query, days=SEARCH_DAYS_BACK)

            try:
                resp = requests.get(url, headers=_HEADERS, timeout=15)
                if resp.status_code != 200:
                    print(f"[indeed] HTTP {resp.status_code} for query: {query}")
                    time.sleep(2)
                    continue

                feed = feedparser.parse(resp.text)
                for entry in feed.entries:
                    job_url = entry.get("link", "")
                    if not job_url or job_url in seen_urls:
                        continue
                    seen_urls.add(job_url)

                    title = entry.get("title", "").split(" - ")[0].strip()
                    # Company / location often packed into title: "Title - Company - City, ST"
                    parts = entry.get("title", "").split(" - ")
                    company = parts[1].strip() if len(parts) > 1 else ""
                    location = parts[2].strip() if len(parts) > 2 else "United States"

                    # Parse date
                    published = entry.get("published", "")
                    date_str = ""
                    if published:
                        try:
                            dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                            date_str = dt.strftime("%Y-%m-%d")
                        except Exception:
                            date_str = published[:10]

                    # Extract description snippet
                    summary_html = entry.get("summary", "")
                    description = BeautifulSoup(summary_html, "lxml").get_text(" ").strip()

                    results.append(JobListing(
                        title=title,
                        company=company,
                        location=location,
                        url=job_url,
                        source=self.name,
                        date_posted=date_str,
                        description=description[:500],
                    ))

                time.sleep(1.5)  # be polite to Indeed
            except Exception as exc:
                print(f"[indeed] Error for query '{query}': {exc}")
                continue

        print(f"[indeed] Found {len(results)} jobs across {len(queries)} queries")
        return results
