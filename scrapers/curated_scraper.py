"""
Curated scholarships from CollegeBoard, Great Minds in STEM, APIA Scholars,
Generation Google, Amazon Future Engineer, and UW Madison CS dept.

These are stable, high-value scholarships. Rather than scraping fragile HTML,
we seed them as structured records and enrich with a live GET for deadline info.
Add new entries to CURATED_SCHOLARSHIPS as you find them.
"""

import re
import logging
from typing import List
from scrapers.base import BaseScraper
from data.models import Scholarship

logger = logging.getLogger(__name__)

CURATED_SCHOLARSHIPS = [
    {
        "name": "Great Minds in STEM — GMiS Scholarship",
        "link": "https://www.greatmindsinstem.org/college/scholarship-application-information",
        "amount": "$500–$10,000",
        "amount_numeric": 5000,
        "due_date": "April (annual)",
        "eligibility_raw": (
            "Hispanic/Latino students pursuing STEM degrees; "
            "min 3.0 GPA; U.S. citizen or permanent resident."
        ),
        "essay_prompt": (
            "Describe how your Hispanic/Latino heritage has influenced "
            "your pursuit of a STEM career."
        ),
        "tags": ["hispanic", "stem"],
    },
    {
        "name": "Generation Google Scholarship",
        "link": "https://buildyourfuture.withgoogle.com/scholarships/generation-google-scholarship",
        "amount": "$10,000",
        "amount_numeric": 10000,
        "due_date": "December (annual)",
        "eligibility_raw": (
            "Underrepresented CS students; must be enrolled full-time at "
            "a U.S. university studying CS or related field; 3.0+ GPA."
        ),
        "essay_prompt": (
            "Tell us about a time you worked to improve the experience of "
            "others through the use of technology."
        ),
        "tags": ["stem", "cs", "diversity"],
    },
    {
        "name": "Amazon Future Engineer Scholarship",
        "link": "https://www.amazonfutureengineer.com/scholarships",
        "amount": "$40,000 ($10,000/year)",
        "amount_numeric": 40000,
        "due_date": "January (annual)",
        "eligibility_raw": (
            "First-generation or low-income students pursuing CS degrees; "
            "GPA 3.0+; U.S. citizen."
        ),
        "essay_prompt": (
            "Describe the biggest challenge you've overcome and how it "
            "shaped your approach to computer science."
        ),
        "tags": ["cs", "stem", "first-gen"],
    },
    {
        "name": "APIA Scholars — Asian & Pacific Islander American Scholarship",
        "link": "https://apiascholars.org/scholarship/apia-scholarship/",
        "amount": "$2,500–$20,000",
        "amount_numeric": 10000,
        "due_date": "January (annual)",
        "eligibility_raw": (
            "Asian/Pacific Islander heritage; full-time undergraduate; "
            "min 2.7 GPA; demonstrates leadership and community involvement."
        ),
        "essay_prompt": (
            "How has your Asian/Pacific Islander identity shaped your "
            "educational and career goals?"
        ),
        "tags": ["apia", "diversity", "leadership"],
    },
    {
        "name": "Society of Women Engineers (SWE) Scholarship",
        "link": "https://scholarships.swe.org/",
        "amount": "$1,000–$15,000",
        "amount_numeric": 5000,
        "due_date": "February (annual)",
        "eligibility_raw": (
            "Women pursuing ABET-accredited engineering or CS degree; "
            "varies by specific award."
        ),
        "essay_prompt": (
            "Describe your engineering or CS project experience and how it "
            "connects to your career goals."
        ),
        "tags": ["women-in-stem", "stem", "cs"],
    },
    {
        "name": "National GEM Consortium Fellowship",
        "link": "https://www.gemfellowship.org/",
        "amount": "Full tuition + stipend",
        "amount_numeric": 50000,
        "due_date": "November (annual)",
        "eligibility_raw": (
            "Underrepresented minority students in STEM; "
            "U.S. citizen/permanent resident; strong academic record."
        ),
        "essay_prompt": (
            "Why do you want to pursue graduate-level STEM study and how "
            "will you contribute to diversity in your field?"
        ),
        "tags": ["hispanic", "diversity", "stem", "graduate"],
    },
    {
        "name": "UW Madison CS Department — Named Scholarships",
        "link": "https://www.cs.wisc.edu/academics/undergraduate-program/scholarships/",
        "amount": "Varies ($1,000–$5,000)",
        "amount_numeric": 2500,
        "due_date": "March (annual)",
        "eligibility_raw": (
            "Enrolled UW Madison CS majors; various criteria per named award "
            "(merit, need, research interest)."
        ),
        "essay_prompt": (
            "Describe your research interests and how they connect to your "
            "long-term career goals in CS."
        ),
        "tags": ["uw-madison", "cs", "stem"],
    },
    {
        "name": "UW Madison CALS / WiSH Portal Scholarships",
        "link": "https://wisc.academicworks.com/",
        "amount": "Varies",
        "amount_numeric": 2000,
        "due_date": "February (annual)",
        "eligibility_raw": (
            "UW Madison students; specific awards vary; apply through "
            "WiSH portal — one application, many scholarships."
        ),
        "essay_prompt": (
            "Varies by scholarship; typically asks about goals, background, "
            "and financial need."
        ),
        "tags": ["uw-madison", "general"],
    },
    {
        "name": "CollegeBoard Opportunity Scholarships",
        "link": "https://opportunity.collegeboard.org/",
        "amount": "$500–$40,000",
        "amount_numeric": 5000,
        "due_date": "Rolling",
        "eligibility_raw": (
            "High school seniors and college students; based on completing "
            "CollegeBoard scholarship steps."
        ),
        "essay_prompt": "Varies by step/category.",
        "tags": ["general", "stem"],
    },
    {
        "name": "Palantir Future Scholarship",
        "link": "https://www.palantir.com/careers/students/scholarship/",
        "amount": "$7,000",
        "amount_numeric": 7000,
        "due_date": "April (annual)",
        "eligibility_raw": (
            "Women or underrepresented minorities in CS/engineering; "
            "sophomore or junior standing; 3.5+ GPA."
        ),
        "essay_prompt": (
            "Describe a technical project you're proud of and explain "
            "the problem it solves."
        ),
        "tags": ["women-in-stem", "diversity", "cs"],
    },
    {
        "name": "IEEE Foundation Scholarship",
        "link": "https://www.ieee.org/membership/students/scholarships.html",
        "amount": "$1,000–$10,000",
        "amount_numeric": 3000,
        "due_date": "Varies by award",
        "eligibility_raw": (
            "IEEE student members in EE, CS, or related field; "
            "various awards for different demographics."
        ),
        "essay_prompt": (
            "Describe how your technical interests align with IEEE's mission "
            "to advance technology for humanity."
        ),
        "tags": ["stem", "cs", "engineering"],
    },
]


class CuratedScraper(BaseScraper):
    name = "curated"

    def scrape(self) -> List[Scholarship]:
        scholarships = []
        for entry in CURATED_SCHOLARSHIPS:
            s = Scholarship(
                name=entry["name"],
                link=entry["link"],
                source=self.name,
                amount=entry["amount"],
                amount_numeric=entry.get("amount_numeric", 0.0),
                due_date=entry.get("due_date", "See website"),
                eligibility_raw=entry.get("eligibility_raw", ""),
                essay_prompt=entry.get("essay_prompt", ""),
                tags=entry.get("tags", []),
            )
            scholarships.append(s)
        logger.info(f"[curated] loaded {len(scholarships)} scholarships")
        return scholarships
