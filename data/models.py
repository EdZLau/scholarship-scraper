"""
Core data model for a scholarship record.
"""

from dataclasses import dataclass, field
from typing import Optional
import json


@dataclass
class Scholarship:
    # Core fields
    name: str
    link: str
    source: str                          # which scraper found it

    # Financial
    amount: str = "Varies"              # keep as string ("$5,000", "Full tuition")
    amount_numeric: float = 0.0         # parsed dollar value for sorting

    # Timing
    due_date: str = "Unknown"
    due_date_sortable: str = "9999-12-31"  # ISO for sorting
    deadline: str = ""
    deadline_type: str = "unknown"
    due_within_30_days: bool = False

    # Eligibility
    eligibility_raw: str = ""
    eligibility_summary: str = ""
    eligibility_note: str = ""
    needs_review: bool = False
    tags: list = field(default_factory=list)   # ["stem", "hispanic", "transfer", ...]

    # Essay
    essay_prompt: str = ""
    sample_essay: str = ""

    # Ranking scores (0–100)
    win_probability: float = 0.0
    alignment_score: float = 0.0
    competitiveness_score: float = 0.0   # lower competition = higher score
    composite_score: float = 0.0

    def to_sheets_row(self) -> list:
        """Return a list matching the Google Sheet column order."""
        return [
            self.name,
            self.deadline or self.due_date,
            self.amount,
            f"{self.win_probability:.0f}%",
            self.eligibility_summary,
            self.needs_review,
            self.essay_prompt,
            self.sample_essay,
            self.link,
            self.deadline_type,
            self.due_within_30_days,
        ]

    def to_dict(self) -> dict:
        return self.__dict__

    @staticmethod
    def sheets_headers() -> list:
        return [
            "Scholarship Name", "Deadline", "Amount",
            "Win Probability", "Eligibility Summary", "Needs Review",
            "Essay Prompt", "Sample Essay", "Link", "Deadline Type",
            "Due Within 30 Days",
        ]
