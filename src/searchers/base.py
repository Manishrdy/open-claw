"""
Base classes shared across all job searchers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from src.resume_parser import CandidateProfile


@dataclass
class JobListing:
    title: str
    company: str
    location: str
    url: str
    source: str                   # e.g. "Greenhouse", "Indeed", "LinkedIn"
    date_posted: str = ""         # ISO date string or human-readable
    description: str = ""         # Full or partial job description
    salary: str = ""


class JobSearcher(ABC):
    """Abstract base class for all job board searchers."""

    name: str = "BaseSearcher"

    @abstractmethod
    def search(self, profile: CandidateProfile) -> list[JobListing]:
        """Search for jobs matching the candidate profile.

        Returns a list of JobListing objects.
        """
        ...

    def _matches_keywords(self, text: str, keywords: list[str], min_hits: int = 1) -> bool:
        """Return True if at least min_hits keywords appear in text (case-insensitive)."""
        text_lower = text.lower()
        hits = sum(1 for kw in keywords if kw.lower() in text_lower)
        return hits >= min_hits
