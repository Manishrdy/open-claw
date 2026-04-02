"""
Resume Parser — extracts candidate profile from PDF resumes using pdfplumber + Gemini.
"""

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

from src.config import GEMINI_API_KEY, GEMINI_MODEL, RESUMES_DIR


@dataclass
class CandidateProfile:
    name: str
    target_roles: list[str]      # e.g. ["AI Engineer", "ML Engineer"]
    skills: list[str]            # e.g. ["Python", "PyTorch", "LLMs"]
    experience_years: int        # total years of experience
    search_keywords: list[str]   # concise keywords to drive search queries
    raw_text: str                # full resume text (for Gemini job matching)


def _extract_pdf_text(pdf_path: Path) -> str:
    """Extract all text from a PDF file."""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
    return "\n\n".join(pages)


def _parse_profile_with_gemini(raw_text: str) -> CandidateProfile:
    """Send resume text to Gemini and extract a structured CandidateProfile."""
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)

    prompt = f"""You are a senior recruiter. Analyze the following resume text and extract structured information.

Return ONLY valid JSON (no markdown, no extra text) with this exact schema:
{{
  "name": "Full name of the candidate",
  "target_roles": ["list", "of", "ideal", "job", "titles"],
  "skills": ["list", "of", "key", "technical", "skills"],
  "experience_years": <integer years of total professional experience>,
  "search_keywords": ["5-10 concise search keywords for job boards, e.g. LLM, GenAI, Python, MLOps"]
}}

Guidelines:
- target_roles should be 3-6 specific job title variants (e.g. "AI Engineer", "LLM Engineer", "Machine Learning Engineer")
- skills should be the top 15-20 technical skills visible in the resume
- search_keywords should be short terms useful for boolean/Google job searches
- experience_years should be an integer (round down)

RESUME TEXT:
---
{raw_text[:12000]}
---"""

    # Retry with exponential backoff for rate-limit errors
    for attempt in range(3):
        try:
            response = model.generate_content(prompt)
            break
        except ResourceExhausted as exc:
            if attempt == 2:
                raise RuntimeError(
                    "Gemini API quota exceeded. Enable billing at https://ai.google.dev "
                    "or wait for daily quota reset."
                ) from exc
            wait = 30 * (attempt + 1)
            print(f"[resume_parser] Rate limited, retrying in {wait}s...")
            time.sleep(wait)

    raw_json = response.text.strip()

    # Strip markdown code fences if Gemini wraps output
    raw_json = re.sub(r"^```(?:json)?\s*", "", raw_json)
    raw_json = re.sub(r"\s*```$", "", raw_json)

    data = json.loads(raw_json)
    return CandidateProfile(
        name=data.get("name", "Candidate"),
        target_roles=data.get("target_roles", []),
        skills=data.get("skills", []),
        experience_years=int(data.get("experience_years", 0)),
        search_keywords=data.get("search_keywords", []),
        raw_text=raw_text,
    )


def load_candidate_profile() -> CandidateProfile:
    """
    Load all PDFs from the resumes directory, extract text, then call Gemini
    to produce a unified CandidateProfile.
    """
    pdf_files = sorted(RESUMES_DIR.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError(f"No PDF resumes found in {RESUMES_DIR}")

    print(f"[resume_parser] Found {len(pdf_files)} resume(s): {[f.name for f in pdf_files]}")

    # Combine text from all resumes (deduplicated by content length — take the longest)
    all_texts = []
    for pdf_path in pdf_files:
        text = _extract_pdf_text(pdf_path)
        if text:
            all_texts.append((len(text), text, pdf_path.name))

    # Use the largest resume as the primary (most content)
    all_texts.sort(reverse=True)
    primary_text = all_texts[0][1]
    primary_name = all_texts[0][2]
    print(f"[resume_parser] Using '{primary_name}' as primary resume ({all_texts[0][0]} chars)")

    profile = _parse_profile_with_gemini(primary_text)
    print(f"[resume_parser] Extracted profile: {profile.name}")
    print(f"  Target roles : {profile.target_roles}")
    print(f"  Skills       : {profile.skills[:8]}...")
    print(f"  Experience   : {profile.experience_years} years")
    print(f"  Keywords     : {profile.search_keywords}")
    return profile
