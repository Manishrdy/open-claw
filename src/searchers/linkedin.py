"""
LinkedIn searcher — uses Gemini with Google Search grounding to find LinkedIn job posts.

LinkedIn blocks direct scraping, so we use Gemini's native Google Search tool
to search for: site:linkedin.com/jobs/view "{role}" "United States"
Gemini returns structured job data extracted from the search results.
"""

import json
import re
import time

import google.generativeai as genai

from src.config import GEMINI_API_KEY, GEMINI_MODEL, SEARCH_DAYS_BACK
from src.resume_parser import CandidateProfile
from src.searchers.base import JobListing, JobSearcher

_SEARCH_QUERIES = [
    'site:linkedin.com/jobs/view "{role}" "United States" -internship',
    'site:linkedin.com/jobs/view "{role}" "Remote" -internship',
]


def _build_linkedin_queries(profile: CandidateProfile) -> list[str]:
    queries = []
    for role in profile.target_roles[:3]:
        for template in _SEARCH_QUERIES:
            queries.append(template.format(role=role))
    return queries


def _extract_jobs_from_gemini_response(text: str, source: str) -> list[dict]:
    """Parse the JSON list of jobs from Gemini's response."""
    # Try to find a JSON array in the response
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return []


class LinkedInSearcher(JobSearcher):
    name = "LinkedIn"

    def search(self, profile: CandidateProfile) -> list[JobListing]:
        genai.configure(api_key=GEMINI_API_KEY)

        # Enable Google Search grounding
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            tools="google_search_retrieval",
        )

        results: list[JobListing] = []
        seen_urls: set[str] = set()
        queries = _build_linkedin_queries(profile)

        for query in queries[:4]:  # limit to 4 searches to conserve quota
            prompt = f"""Search Google for this exact query and return job listings found:
Query: {query}

For each job listing found, extract and return a JSON array with objects:
[
  {{
    "title": "exact job title",
    "company": "company name",
    "location": "location string",
    "url": "full linkedin.com/jobs/view/... URL",
    "date_posted": "date if visible, else empty string"
  }}
]

Return ONLY the JSON array, no other text. If no jobs found, return [].
Focus on results from the past {SEARCH_DAYS_BACK} days if possible."""

            try:
                response = model.generate_content(prompt)
                raw_text = response.text.strip()
                jobs_data = _extract_jobs_from_gemini_response(raw_text, "LinkedIn")

                for job in jobs_data:
                    url = job.get("url", "")
                    if not url or "linkedin.com" not in url or url in seen_urls:
                        continue
                    seen_urls.add(url)

                    results.append(JobListing(
                        title=job.get("title", ""),
                        company=job.get("company", ""),
                        location=job.get("location", "United States"),
                        url=url,
                        source=self.name,
                        date_posted=job.get("date_posted", ""),
                    ))

                time.sleep(2)  # respect Gemini rate limits
            except Exception as exc:
                print(f"[linkedin] Error for query '{query}': {exc}")
                continue

        print(f"[linkedin] Found {len(results)} jobs via Gemini search grounding")
        return results
