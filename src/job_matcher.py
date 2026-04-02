"""
Job Matcher — uses Gemini to score each job listing against the candidate's resume profile.
Returns an enriched JobMatch dataclass with score, matched/missing skills, and reasoning.
"""

import json
import re
import time
from dataclasses import dataclass

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

from src.config import GEMINI_API_KEY, GEMINI_FLASH_MODEL, MIN_MATCH_SCORE, MAX_JOBS_TO_SCORE
from src.resume_parser import CandidateProfile
from src.searchers.base import JobListing


@dataclass
class JobMatch:
    listing: JobListing
    score: int               # 0–100
    matched_skills: str      # comma-separated
    missing_skills: str      # comma-separated
    reason: str              # brief Gemini explanation


def _score_job(
    model: genai.GenerativeModel,
    job: JobListing,
    profile: CandidateProfile,
) -> JobMatch | None:
    """Ask Gemini to score a single job vs the candidate profile."""

    job_info = f"""Job Title: {job.title}
Company: {job.company}
Location: {job.location}
Source: {job.source}
Description: {job.description[:1500] if job.description else 'N/A'}"""

    resume_summary = f"""Candidate: {profile.name}
Target Roles: {', '.join(profile.target_roles)}
Skills: {', '.join(profile.skills)}
Experience: {profile.experience_years} years
Keywords: {', '.join(profile.search_keywords)}"""

    prompt = f"""You are a professional recruiter. Score how well this job matches the candidate.

CANDIDATE PROFILE:
{resume_summary}

JOB LISTING:
{job_info}

Return ONLY valid JSON (no markdown):
{{
  "score": <integer 0-100>,
  "matched_skills": "<comma-separated skills that match>",
  "missing_skills": "<comma-separated key requirements the candidate may lack>",
  "reason": "<1-2 sentence explanation of the score>"
}}

Scoring guide:
- 80-100: Excellent match — title and most skills align
- 60-79: Good match — role fits, minor skill gaps
- 40-59: Partial match — some overlap but significant gaps
- 0-39: Poor match — different domain or seniority level"""

    try:
        for attempt in range(3):
            try:
                response = model.generate_content(prompt)
                break
            except ResourceExhausted:
                if attempt == 2:
                    raise
                time.sleep(30 * (attempt + 1))
        raw = response.text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)

        return JobMatch(
            listing=job,
            score=int(data.get("score", 0)),
            matched_skills=data.get("matched_skills", ""),
            missing_skills=data.get("missing_skills", ""),
            reason=data.get("reason", ""),
        )
    except Exception as exc:
        print(f"[job_matcher] Error scoring '{job.title}' at {job.company}: {exc}")
        return None


def match_jobs(
    listings: list[JobListing],
    profile: CandidateProfile,
) -> list[JobMatch]:
    """
    Score all job listings against the candidate profile.
    Filters out jobs below MIN_MATCH_SCORE.
    Returns JobMatch list sorted by score descending.
    """
    genai.configure(api_key=GEMINI_API_KEY)
    # Use the faster/cheaper Flash model for bulk scoring
    model = genai.GenerativeModel(GEMINI_FLASH_MODEL)

    # Deduplicate listings by URL before scoring
    seen_urls: set[str] = set()
    unique_listings = []
    for job in listings:
        if job.url and job.url not in seen_urls:
            seen_urls.add(job.url)
            unique_listings.append(job)

    total = min(len(unique_listings), MAX_JOBS_TO_SCORE)
    print(f"[job_matcher] Scoring {total} unique listings (cap: {MAX_JOBS_TO_SCORE})")

    matches: list[JobMatch] = []
    for i, job in enumerate(unique_listings[:total]):
        if i > 0 and i % 10 == 0:
            print(f"[job_matcher] Progress: {i}/{total}")
            time.sleep(1)  # brief pause every 10 calls

        match = _score_job(model, job, profile)
        if match and match.score >= MIN_MATCH_SCORE:
            matches.append(match)

        time.sleep(0.5)  # polite rate limit for Gemini

    matches.sort(key=lambda m: m.score, reverse=True)
    print(f"[job_matcher] {len(matches)} jobs scored >= {MIN_MATCH_SCORE}")
    return matches
