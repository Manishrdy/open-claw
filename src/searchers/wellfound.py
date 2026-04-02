"""
Wellfound (AngelList Talent) searcher.
Uses Wellfound's public job search page scraping with requests + BeautifulSoup.
Wellfound URL pattern: https://wellfound.com/jobs?roles[]={role_slug}&locations[]={loc}
"""

import time
import urllib.parse

import requests
from bs4 import BeautifulSoup

from src.resume_parser import CandidateProfile
from src.searchers.base import JobListing, JobSearcher

_BASE_URL = "https://wellfound.com/jobs"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Wellfound role slugs that map to common AI/ML roles
_ROLE_SLUG_MAP = {
    "AI Engineer": "machine-learning-engineer",
    "ML Engineer": "machine-learning-engineer",
    "Machine Learning Engineer": "machine-learning-engineer",
    "LLM Engineer": "machine-learning-engineer",
    "Data Scientist": "data-scientist",
    "Software Engineer": "software-engineer",
    "Backend Engineer": "backend-engineer",
    "Full Stack Engineer": "full-stack-engineer",
    "MLOps Engineer": "devops-engineer",
    "AI Researcher": "machine-learning-engineer",
}


def _get_role_slug(role: str) -> str:
    for key, slug in _ROLE_SLUG_MAP.items():
        if key.lower() in role.lower():
            return slug
    return "software-engineer"


def _scrape_wellfound_page(url: str) -> list[dict]:
    """Scrape a Wellfound jobs listing page and return raw job dicts."""
    jobs = []
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        if resp.status_code != 200:
            return jobs

        soup = BeautifulSoup(resp.text, "lxml")

        # Wellfound job cards
        # Selector targets the individual job listing divs
        job_cards = soup.select("div[data-test='StartupResult']")
        if not job_cards:
            # Fallback: try generic job card selectors
            job_cards = soup.select("div.styles_jobsListItem__pPHYM, div[class*='jobListing']")

        for card in job_cards:
            title_el = card.select_one("a[class*='JobListing'] span, h2 a, a[data-test='job-link']")
            company_el = card.select_one("a[data-test='startup-link'], h3 a, span[class*='company']")
            location_el = card.select_one("span[class*='location'], div[class*='location']")

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else ""
            location = location_el.get_text(strip=True) if location_el else "United States"

            # Get URL
            link_el = card.select_one("a[href*='/jobs/']")
            job_url = ""
            if link_el:
                href = link_el.get("href", "")
                job_url = f"https://wellfound.com{href}" if href.startswith("/") else href

            if title:
                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "url": job_url,
                })

    except Exception as exc:
        print(f"[wellfound] Scrape error for {url}: {exc}")

    return jobs


class WellfoundSearcher(JobSearcher):
    name = "Wellfound"

    def search(self, profile: CandidateProfile) -> list[JobListing]:
        results: list[JobListing] = []
        seen_urls: set[str] = set()
        seen_roles: set[str] = set()

        for role in profile.target_roles[:3]:
            slug = _get_role_slug(role)
            if slug in seen_roles:
                continue
            seen_roles.add(slug)

            params = urllib.parse.urlencode({
                "roles[]": slug,
                "locations[]": "United States",
                "remote": "true",
            })
            url = f"{_BASE_URL}?{params}"

            raw_jobs = _scrape_wellfound_page(url)
            for job in raw_jobs:
                job_url = job.get("url", "")
                if not job_url or job_url in seen_urls:
                    continue
                seen_urls.add(job_url)

                # Basic keyword filter
                keywords = [kw.lower() for kw in profile.search_keywords + profile.target_roles]
                if not self._matches_keywords(job["title"], keywords, min_hits=1):
                    continue

                results.append(JobListing(
                    title=job["title"],
                    company=job["company"],
                    location=job.get("location", "United States"),
                    url=job_url,
                    source=self.name,
                ))

            time.sleep(2)

        print(f"[wellfound] Found {len(results)} matching jobs")
        return results
