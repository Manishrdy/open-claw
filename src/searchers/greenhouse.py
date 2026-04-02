"""
Greenhouse searcher — uses the public Greenhouse boards JSON API.
No authentication required. Covers hundreds of tech companies.
"""

import time
import requests

from src.config import GREENHOUSE_COMPANY_SLUGS, LOCATIONS
from src.resume_parser import CandidateProfile
from src.searchers.base import JobListing, JobSearcher

_BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
_JOB_URL = "https://boards.greenhouse.io/{slug}/jobs/{job_id}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobSearchBot/1.0)"}


class GreenhouseSearcher(JobSearcher):
    name = "Greenhouse"

    def search(self, profile: CandidateProfile) -> list[JobListing]:
        results: list[JobListing] = []
        keywords = [kw.lower() for kw in profile.search_keywords + profile.target_roles]

        for slug in GREENHOUSE_COMPANY_SLUGS:
            try:
                resp = requests.get(
                    _BASE_URL.format(slug=slug),
                    headers=_HEADERS,
                    timeout=10,
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
                jobs = data.get("jobs", [])
                for job in jobs:
                    title = job.get("title", "")
                    location_name = ""
                    offices = job.get("offices", [])
                    if offices:
                        location_name = offices[0].get("name", "")

                    # Filter by keyword match on title
                    if not self._matches_keywords(title, keywords, min_hits=1):
                        continue

                    # Filter by location (USA / Remote)
                    loc_lower = location_name.lower()
                    if not any(
                        loc.lower() in loc_lower or loc_lower == "" or "remote" in loc_lower
                        for loc in LOCATIONS
                    ):
                        # Accept empty location (might be fully remote)
                        if location_name and "remote" not in loc_lower:
                            # Check if any LOCATION keyword appears
                            us_terms = ["united states", "usa", "us ", "remote", "anywhere"]
                            if not any(t in loc_lower for t in us_terms):
                                continue

                    job_id = job.get("id", "")
                    url = _JOB_URL.format(slug=slug, job_id=job_id)

                    results.append(JobListing(
                        title=title,
                        company=slug.replace("-", " ").title(),
                        location=location_name or "Remote / Not specified",
                        url=url,
                        source=self.name,
                        date_posted=job.get("updated_at", "")[:10],
                    ))

                time.sleep(0.3)  # polite rate limit
            except Exception as exc:
                print(f"[greenhouse] Error for {slug}: {exc}")
                continue

        print(f"[greenhouse] Found {len(results)} matching jobs")
        return results
