"""
Ashby HQ searcher — uses Ashby's public job board API.
Each company has a public endpoint: GET https://api.ashbyhq.com/posting-public/apiKey/job-board
The "apiKey" here is actually the company's public slug/token — visible in the URL of their job board.
"""

import time
import requests

from src.config import ASHBY_COMPANY_SLUGS
from src.resume_parser import CandidateProfile
from src.searchers.base import JobListing, JobSearcher

_API_URL = "https://api.ashbyhq.com/posting-public/{slug}/job-board?includeCompensation=true"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobSearchBot/1.0)"}


class AshbySearcher(JobSearcher):
    name = "Ashby"

    def search(self, profile: CandidateProfile) -> list[JobListing]:
        results: list[JobListing] = []
        keywords = [kw.lower() for kw in profile.search_keywords + profile.target_roles]

        for slug in ASHBY_COMPANY_SLUGS:
            try:
                resp = requests.get(
                    _API_URL.format(slug=slug),
                    headers=_HEADERS,
                    timeout=10,
                )
                if resp.status_code != 200:
                    continue

                data = resp.json()
                job_postings = data.get("jobPostings", [])

                for job in job_postings:
                    title = job.get("title", "")
                    if not self._matches_keywords(title, keywords, min_hits=1):
                        continue

                    location = job.get("locationName", "")
                    loc_lower = location.lower()
                    us_terms = ["united states", "usa", "us", "remote", "anywhere", ""]
                    if not any(t in loc_lower for t in us_terms):
                        continue

                    # Build job URL
                    job_id = job.get("id", "")
                    apply_url = job.get("applyUrl") or job.get("jobUrl") or \
                        f"https://jobs.ashbyhq.com/{slug}/{job_id}"

                    # Salary range
                    comp = job.get("compensation", {}) or {}
                    salary = ""
                    if comp:
                        min_val = comp.get("minValue")
                        max_val = comp.get("maxValue")
                        currency = comp.get("currencyCode", "USD")
                        interval = comp.get("interval", "")
                        if min_val and max_val:
                            salary = f"{currency} {min_val:,}–{max_val:,} {interval}"

                    results.append(JobListing(
                        title=title,
                        company=slug.replace("-", " ").title(),
                        location=location or "Remote / Not specified",
                        url=apply_url,
                        source=self.name,
                        date_posted=job.get("publishedDate", "")[:10],
                        salary=salary,
                    ))

                time.sleep(0.3)
            except Exception as exc:
                print(f"[ashby] Error for {slug}: {exc}")
                continue

        print(f"[ashby] Found {len(results)} matching jobs")
        return results
