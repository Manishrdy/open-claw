"""
Recently-funded startups searcher — uses Gemini with Google Search grounding
to discover startups that recently raised funding AND are hiring for matching roles.

Queries:
  - "Series A" OR "Series B" 2025 hiring "{role}" startup USA
  - site:techcrunch.com "raises" "hires" "{role}" 2025
  - site:wellfound.com "{role}" "recently funded"
"""

import json
import re
import time

import google.generativeai as genai

from src.config import GEMINI_API_KEY, GEMINI_MODEL
from src.resume_parser import CandidateProfile
from src.searchers.base import JobListing, JobSearcher

_SEARCH_TEMPLATES = [
    '"Series A" OR "Series B" OR "seed round" 2025 hiring "{role}" startup "United States"',
    'site:techcrunch.com "{role}" OR "AI startup" hiring 2025',
    'recently funded AI startup hiring "{role}" 2026 USA',
    '"raised" "million" hiring "{role}" GenAI OR LLM startup 2025 OR 2026',
]


def _extract_jobs_from_text(text: str) -> list[dict]:
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return []


class FundedStartupsSearcher(JobSearcher):
    name = "FundedStartups"

    def search(self, profile: CandidateProfile) -> list[JobListing]:
        genai.configure(api_key=GEMINI_API_KEY)

        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            tools="google_search_retrieval",
        )

        results: list[JobListing] = []
        seen_urls: set[str] = set()

        primary_role = profile.target_roles[0] if profile.target_roles else "AI Engineer"
        queries = [t.format(role=primary_role) for t in _SEARCH_TEMPLATES[:3]]

        for query in queries:
            prompt = f"""Use Google Search to find this query:
{query}

Based on the search results, identify startups that:
1. Recently received funding (Seed, Series A, Series B, or Series C in 2025-2026)
2. Are actively hiring for roles similar to: {', '.join(profile.target_roles)}
3. Are based in USA or are remote-friendly

For each company/job opening you find, return a JSON array:
[
  {{
    "title": "job title (infer if not explicit, e.g. 'AI Engineer')",
    "company": "startup company name",
    "location": "location or 'Remote' or 'USA'",
    "url": "direct URL to job posting or company careers page",
    "funding_stage": "Series A / Seed / etc.",
    "date_posted": "date if visible, else empty string"
  }}
]

Return ONLY the JSON array. If nothing relevant found, return [].
Prioritize actual job posting URLs over generic company URLs."""

            try:
                response = model.generate_content(prompt)
                raw_text = response.text.strip()
                jobs_data = _extract_jobs_from_text(raw_text)

                for job in jobs_data:
                    url = job.get("url", "")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)

                    funding = job.get("funding_stage", "")
                    company = job.get("company", "")
                    if funding:
                        company = f"{company} ({funding})"

                    results.append(JobListing(
                        title=job.get("title", ""),
                        company=company,
                        location=job.get("location", "USA"),
                        url=url,
                        source=self.name,
                        date_posted=job.get("date_posted", ""),
                    ))

                time.sleep(3)  # longer pause between Gemini grounding calls
            except Exception as exc:
                print(f"[funded_startups] Error for query: {exc}")
                continue

        print(f"[funded_startups] Found {len(results)} leads from funded startups")
        return results
