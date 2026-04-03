
import time
from pydantic import BaseModel, Field

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

from src.config import GEMINI_API_KEY, GEMINI_FLASH_MODEL, MIN_MATCH_SCORE, MAX_JOBS_TO_SCORE
from src.resume_parser import CandidateProfile
from src.searchers.base import JobListing
from src.job_matcher import JobMatch


class JobScoreOutput(BaseModel):
    score: int = Field(description="Match score from 0 to 100")
    matched_skills: str = Field(description="Comma-separated skills that match the job")
    missing_skills: str = Field(description="Comma-separated key requirements the candidate lacks")
    reason: str = Field(description="1-2 sentence explanation of the score")

SCORING_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a professional recruiter. Score how well a job matches a candidate.\n"
        "Respond with ONLY valid JSON matching this schema:\n"
        "{format_instructions}",
    ),
    (
        "human",
        "CANDIDATE PROFILE:\n"
        "Candidate: {name}\n"
        "Target Roles: {target_roles}\n"
        "Skills: {skills}\n"
        "Experience: {experience_years} years\n"
        "Keywords: {search_keywords}\n"
        "\n"
        "JOB LISTING:\n"
        "Job Title: {job_title}\n"
        "Company: {company}\n"
        "Location: {location}\n"
        "Source: {source}\n"
        "Description: {description}\n"
        "\n"
        "Scoring guide:\n"
        "- 80-100: Excellent match — title and most skills align\n"
        "- 60-79: Good match — role fits, minor skill gaps\n"
        "- 40-59: Partial match — some overlap but significant gaps\n"
        "- 0-39: Poor match — different domain or seniority level",
    ),
])

def build_scoring_chain():
    llm = ChatGoogleGenerativeAI(
        model=GEMINI_FLASH_MODEL,
        google_api_key=GEMINI_API_KEY,
        temperature=0,       # deterministic for consistent scoring
        max_retries=3,       # built-in retry on transient/rate-limit errors
    )

    parser = PydanticOutputParser(pydantic_object=JobScoreOutput)

    chain = SCORING_PROMPT | llm | parser

    return chain, parser

def _prepare_chain_input(
    job: JobListing,
    profile: CandidateProfile,
    format_instructions: str,
) -> dict:
    return {
        "format_instructions": format_instructions,
        "name": profile.name,
        "target_roles": ", ".join(profile.target_roles),
        "skills": ", ".join(profile.skills),
        "experience_years": profile.experience_years,
        "search_keywords": ", ".join(profile.search_keywords),
        "job_title": job.title,
        "company": job.company,
        "location": job.location,
        "source": job.source,
        "description": (job.description[:1500] if job.description else "N/A"),
    }

def match_jobs_langchain(
    listings: list[JobListing],
    profile: CandidateProfile,
) -> list[JobMatch]:
    chain, parser = build_scoring_chain()
    format_instructions = parser.get_format_instructions()

    seen_urls: set[str] = set()
    unique_listings = []
    for job in listings:
        if job.url and job.url not in seen_urls:
            seen_urls.add(job.url)
            unique_listings.append(job)

    total = min(len(unique_listings), MAX_JOBS_TO_SCORE)
    print(f"[langchain_scorer] Scoring {total} unique listings (cap: {MAX_JOBS_TO_SCORE})")

    matches: list[JobMatch] = []
    for i, job in enumerate(unique_listings[:total]):
        if i > 0 and i % 10 == 0:
            print(f"[langchain_scorer] Progress: {i}/{total}")
            time.sleep(1)  # brief pause every 10 calls

        try:
            chain_input = _prepare_chain_input(job, profile, format_instructions)
            result: JobScoreOutput = chain.invoke(chain_input)

            if result.score >= MIN_MATCH_SCORE:
                matches.append(JobMatch(
                    listing=job,
                    score=result.score,
                    matched_skills=result.matched_skills,
                    missing_skills=result.missing_skills,
                    reason=result.reason,
                ))
        except Exception as exc:
            print(f"[langchain_scorer] Error scoring '{job.title}' at {job.company}: {exc}")

        time.sleep(0.5)

    matches.sort(key=lambda m: m.score, reverse=True)
    print(f"[langchain_scorer] {len(matches)} jobs scored >= {MIN_MATCH_SCORE}")
    return matches
