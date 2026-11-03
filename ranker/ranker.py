"""
Ranking engine.
Computes win_probability, alignment_score, competitiveness_score,
and a composite score for each scholarship against the user's profile.
"""

import re
import logging
from datetime import date
from typing import List
from data.models import Scholarship
from config.profile import PROFILE

logger = logging.getLogger(__name__)

# ── Tag → profile weight mapping ─────────────────────────────────────────────
TAG_WEIGHTS = {
    "hispanic":      30,   # strong identity match
    "women-in-stem": 20,
    "stem":          15,
    "cs":            18,
    "transfer":      25,   # direct match
    "uw-madison":    20,   # current school
    "biotech":       12,
    "neurotech":     12,
    "apia":           0,   # does not apply — zero weight
    "first-gen":     -5,   # slight mismatch (not first gen)
    "diversity":     10,
    "leadership":    10,
    "general":        8,
    "graduate":      -10,  # not relevant yet
    "engineering":   10,
}

# ── Interest keyword → scholarship text matching ─────────────────────────────
INTEREST_KEYWORDS = [
    "artificial intelligence", "machine learning", "ai", "ml",
    "neurotech", "brain-computer", "bci",
    "biotech", "biomedical", "biologics",
    "semiconductor", "hardware",
    "surgical robotics", "robotics",
    "computer science", "software",
]

# Competitiveness estimates (applicant pool size, rough industry knowledge)
COMPETITIVENESS_MAP = {
    "curated": {
        "Great Minds in STEM": 60,      # moderate pool, niche Hispanic STEM
        "Generation Google": 40,         # large pool, competitive
        "Amazon Future Engineer": 35,
        "APIA Scholars": 55,
        "Society of Women Engineers": 50,
        "GEM": 30,
        "UW Madison CS": 65,
        "WiSH Portal": 70,
        "CollegeBoard": 50,
        "Palantir": 45,
        "IEEE": 55,
    }
}


def rank_scholarships(scholarships: List[Scholarship]) -> List[Scholarship]:
    """Filter, score, and sort scholarships. Mutates each Scholarship in place."""
    eligible = []
    excluded = []
    for s in scholarships:
        reasons, s.needs_review = _eligibility_assessment(s)
        if s.deadline_type == "exact" and s.deadline:
            try:
                deadline = date.fromisoformat(s.deadline)
            except ValueError:
                s.needs_review = True
            else:
                days_until_deadline = (deadline - date.today()).days
                if days_until_deadline < 0:
                    reasons.append(f"deadline passed on {deadline.isoformat()}")
                s.due_within_30_days = 0 <= days_until_deadline <= 30
        else:
            s.due_within_30_days = False
        if reasons:
            excluded.append((s.name, reasons))
            continue
        eligible.append(s)

    logger.info("[ranker] excluded %d ineligible scholarships", len(excluded))
    for name, reasons in excluded:
        logger.warning("[ranker] excluded %r: %s", name, "; ".join(reasons))

    for s in eligible:
        s.alignment_score = _alignment_score(s)
        s.competitiveness_score = _competitiveness_score(s)
        s.win_probability = _win_probability(s)
        s.composite_score = _composite(s)

    eligible.sort(key=lambda s: s.win_probability, reverse=True)
    logger.info(
        "[ranker] ranked %d scholarships (%d flagged for eligibility review)",
        len(eligible),
        sum(s.needs_review for s in eligible),
    )
    return eligible


def _eligibility_assessment(s: Scholarship) -> tuple[list[str], bool]:
    """Return definite ineligibility reasons and whether the record needs review."""
    normalized = s.eligibility_raw.strip().lower()
    reasons = []
    needs_review = s.needs_review or not bool(normalized)
    if re.search(
        r"\b(?:varies by (?:specific )?award|specific awards? vary|"
        r"criteria vary|various criteria|criteria per named award|different demographics|"
        r"depending on the award|scholarship steps)\b",
        normalized,
    ):
        needs_review = True

    def unknown_or_mismatch(profile_key: str, requirement: str, matches: bool) -> None:
        nonlocal needs_review
        value = PROFILE.get(profile_key)
        if value is None or value == "":
            needs_review = True
        elif not matches:
            reasons.append(requirement)

    # Handle a common disjunction as one condition: either eligibility path
    # suffices, and an unknown alternative only matters if neither is met.
    women_or_minority = re.search(
        r"\b(?:women|woman|female)\b.{0,60}\bor\b.{0,60}"
        r"\b(?:underrepresented minorit(?:y|ies)|minority)\b",
        normalized,
    )
    ethnicity_patterns = {
        "hispanic": r"\b(?:hispanic|latino|latina|latine)\b",
        "asian": r"\basian\b",
        "pacific islander": r"\bpacific islander\b",
        "black": r"\b(?:black|african american)\b",
        "native": r"\b(?:native american|american indian|alaska native)\b",
        "native hawaiian": r"\bnative hawaiian\b",
    }
    ethnicity_text = normalized
    if re.search(r"\bscholarship\b", s.name, re.I):
        ethnicity_text += " " + s.name.lower()
    ethnicity_value = PROFILE.get("ethnicity")
    profile_ethnicity = (
        ethnicity_value.lower()
        if isinstance(ethnicity_value, str)
        else " ".join(ethnicity_value or []).lower()
    )
    matching_ethnicity = any(
        re.search(pattern, profile_ethnicity) for pattern in ethnicity_patterns.values()
    )
    underrepresented = bool(
        re.search(r"\bunderrepresented minorit(?:y|ies)\b", normalized)
    )
    if women_or_minority:
        gender = PROFILE.get("gender")
        gender_matches = (
            str(gender).lower() in {"female", "woman"}
            if gender is not None else None
        )
        ethnicity = PROFILE.get("ethnicity")
        minority_matches = matching_ethnicity if ethnicity else None
        if gender_matches is True or (underrepresented and minority_matches is True):
            pass
        elif gender_matches is False and (
            not underrepresented or minority_matches is False
        ):
            reasons.append("requires women or an underrepresented minority")
        else:
            needs_review = True
    else:
        name_gender_restriction = re.search(
            r"\b(?:women|woman|female|men|man|male)\b.{0,50}\bscholarship\b"
            r"|\bscholarship\b.{0,30}\b(?:for women|for men)\b",
            s.name.lower(),
        )
        gender_text = normalized
        if name_gender_restriction:
            gender_text += " " + s.name.lower()
        requires_women = bool(re.search(r"\b(?:women|woman|female)\b", gender_text))
        requires_men = bool(re.search(r"\b(?:men|man|male)\b", gender_text))
        gender = PROFILE.get("gender")
        gender_value = str(gender).lower() if gender is not None else ""
        gender_requirement = None
        if requires_women and not requires_men:
            gender_requirement = ("gender", "requires women", gender_value in {"female", "woman"})
        elif requires_men and not requires_women:
            gender_requirement = ("gender", "requires men", gender_value in {"male", "man"})
        if gender_requirement:
            key, reason, matches = gender_requirement
            unknown_or_mismatch(key, reason, matches)

        required_ethnicities = [
            group for group, pattern in ethnicity_patterns.items()
            if re.search(pattern, ethnicity_text)
        ]
        if required_ethnicities:
            if not PROFILE.get("ethnicity"):
                needs_review = True
            elif not any(
                re.search(ethnicity_patterns[group], profile_ethnicity)
                for group in required_ethnicities
            ):
                reasons.append(
                    "requires " + " or ".join(required_ethnicities)
                    + ", which does not match the profile"
                )
        elif underrepresented:
            if not PROFILE.get("ethnicity"):
                needs_review = True
            elif not matching_ethnicity:
                reasons.append("requires an underrepresented minority identity")

    # GPA minimums.
    gpa_values = re.findall(
        r"(?:min(?:imum)?\.?\s*|at least\s*)(\d(?:\.\d+)?)\s*(?:\+\s*)?(?:gpa)?"
        r"|\bgpa\s*(?:of\s*)?(\d(?:\.\d+)?)\s*\+?"
        r"|\b(\d(?:\.\d+)?)\s*\+\s*gpa\b",
        normalized,
    )
    minimums = [float(value) for pair in gpa_values for value in pair if value]
    if minimums and PROFILE.get("gpa") is None:
        needs_review = True
    elif minimums:
        required_gpa = max(minimums)
        if PROFILE["gpa"] < required_gpa:
            reasons.append(f"requires GPA {required_gpa:.1f}; profile GPA is {PROFILE['gpa']}")

    # Citizenship, enrollment status, and membership are only assessed when
    # the corresponding fact has been supplied in the profile.
    requires_citizen_or_resident = bool(re.search(
        r"\b(?:u\.s\. citizens?|us citizens?)\b.{0,50}\bpermanent resident\b"
        r"|\bpermanent resident\b.{0,50}\b(?:u\.s\. citizens?|us citizens?)\b",
        normalized,
    ))
    requires_citizenship = bool(re.search(
        r"\b(?:u\.s\. citizens?|us citizens?|citizenship required)\b", normalized
    ))
    requires_residency = bool(re.search(r"\bpermanent resident\b", normalized))
    us_citizen = PROFILE.get("us_citizen")
    permanent_resident = PROFILE.get("permanent_resident")
    if requires_citizen_or_resident:
        if us_citizen is True or permanent_resident is True:
            pass
        elif us_citizen is False and permanent_resident is False:
            reasons.append("requires U.S. citizenship or permanent residency")
        else:
            needs_review = True
    else:
        if requires_citizenship:
            unknown_or_mismatch(
                "us_citizen", "requires U.S. citizenship", us_citizen is True
            )
        if requires_residency:
            if permanent_resident is None:
                if us_citizen is not True:
                    needs_review = True
            elif not permanent_resident and us_citizen is not True:
                reasons.append("requires permanent residency or U.S. citizenship")
    if re.search(r"\bfull[- ]time\b", normalized):
        unknown_or_mismatch(
            "full_time", "requires full-time enrollment", PROFILE.get("full_time") is True
        )
    if re.search(r"\bIEEE student members?\b", normalized, re.I):
        unknown_or_mismatch(
            "ieee_member", "requires IEEE student membership",
            PROFILE.get("ieee_member") is True,
        )

    # Current school restrictions.
    current_school = str(PROFILE.get("school") or "").lower()
    school_aliases = (
        "uw madison", "university of wisconsin-madison",
        "university of wisconsin madison", "wisconsin-madison",
    )
    if any(alias in normalized for alias in school_aliases):
        if current_school and any(alias in current_school for alias in school_aliases):
            pass
        elif current_school:
            reasons.append("requires enrollment at UW-Madison")
        else:
            needs_review = True

    # State-residency requirements. The configured state is used as provided;
    # other state references outside residency language are not restrictions.
    states = (
        "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
        "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
        "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
        "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
        "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
        "New Hampshire", "New Jersey", "New Mexico", "New York",
        "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
        "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
        "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
        "West Virginia", "Wisconsin", "Wyoming",
    )
    profile_state = str(PROFILE.get("state_residency") or "").lower()
    for state_name in states:
        state = state_name.lower()
        restriction = re.search(
            rf"\b(?:resident of|residents of|reside in|residents? in|"
            rf"live in|living in|from)\s+{re.escape(state)}\b"
            rf"|\b{re.escape(state)}\s+residents?\b",
            normalized,
        )
        if restriction:
            if not profile_state:
                needs_review = True
            elif profile_state != state:
                reasons.append(f"requires {state_name} residency")

    # Major, student year, and transfer requirements.
    major = str(PROFILE.get("major") or "").lower()
    if re.search(r"\bstem\s+(?:degree|degrees|field|major|students?)\b", normalized):
        if PROFILE.get("stem_background") is False:
            reasons.append("requires a STEM field of study")
    if re.search(r"\bcomputer science\b|\bcs\b", normalized):
        if not major:
            needs_review = True
        elif "computer science" not in major and not re.search(r"\bcs\b", major):
            reasons.append("requires a computer science major")
    elif re.search(
        r"\bengineering\s+(?:majors?|degree|field|students?)\b"
        r"|\bpursuing an? engineering\b|\bstudents? in engineering\b",
        normalized,
    ):
        if not major:
            needs_review = True
        elif "engineering" not in major:
            reasons.append("requires an engineering major")

    classification = str(PROFILE.get("classification", "")).lower()
    if re.search(r"\bgraduate[- ]level\b|\bgraduate students?\b", normalized):
        if not classification:
            needs_review = True
        elif "graduate" not in classification:
            reasons.append("requires graduate-level study")
    if re.search(r"\bhigh school seniors?\b", normalized) and not re.search(
        r"\b(?:and|or)\s+college students?\b", normalized
    ):
        if not classification:
            needs_review = True
        elif "high school" not in classification:
            reasons.append("requires high-school senior standing")
    class_levels = set(re.findall(r"\b(?:sophomore|junior|senior)\b", normalized))
    if class_levels and not re.search(r"\bhigh school seniors?\b", normalized):
        if not classification:
            needs_review = True
        elif not any(level in classification for level in class_levels):
            reasons.append(f"requires {', '.join(sorted(class_levels))} standing")
    if re.search(r"\btransfer students?\b|\btransfer applicants?\b", normalized):
        is_transfer = bool(
            PROFILE.get("transfer_from")
            or "transfer" in classification
            or PROFILE.get("transfer") is True
        )
        if PROFILE.get("transfer_from") is None and not classification and PROFILE.get("transfer") is None:
            needs_review = True
        elif not is_transfer:
            reasons.append("requires transfer-student status")

    # First-generation and financial-need alternatives.
    requires_first_gen = bool(re.search(r"\bfirst[- ]generation\b", normalized))
    requires_low_income = bool(re.search(r"\b(?:low[- ]income|financial need)\b", normalized))
    first_gen = PROFILE.get("first_gen")
    financial_need = PROFILE.get("financial_need")
    if requires_first_gen and requires_low_income and re.search(
        r"\bfirst[- ]generation\b.{0,50}\bor\b.{0,50}\b(?:low[- ]income|financial need)\b",
        normalized,
    ):
        if first_gen is True or financial_need is True:
            pass
        elif first_gen is None or financial_need is None:
            needs_review = True
        else:
            reasons.append("requires first-generation status or financial need")
    else:
        if requires_first_gen:
            unknown_or_mismatch(
                "first_gen", "requires first-generation status", first_gen is True
            )
        if requires_low_income:
            unknown_or_mismatch(
                "financial_need", "requires low-income status or financial need",
                financial_need is True,
            )

    if re.search(r"\b(?:at least|minimum age|aged?)\s+\d{2}\b", normalized):
        needs_review = True

    return reasons, needs_review


def _alignment_score(s: Scholarship) -> float:
    """0–100. How well does this scholarship match the profile?"""
    score = 0.0

    # Tag-based alignment
    for tag in s.tags:
        score += TAG_WEIGHTS.get(tag, 5)

    # Text-based interest matching against name + eligibility + essay prompt
    combined = f"{s.name} {s.eligibility_raw} {s.essay_prompt}".lower()
    interest_hits = sum(1 for kw in INTEREST_KEYWORDS if kw in combined)
    score += interest_hits * 4

    # GPA bonus (assume profile GPA is competitive)
    if PROFILE["gpa"] >= 3.5:
        score += 8
    elif PROFILE["gpa"] >= 3.0:
        score += 4

    # Transfer bonus
    if "transfer" in s.tags or "transfer" in combined:
        score += 10

    return min(score, 100.0)


def _competitiveness_score(s: Scholarship) -> float:
    """
    0–100. Higher = LESS competitive (better odds for you).
    Estimated from award size, source type, and tag specificity.
    """
    base = 50.0

    # More specific tags = smaller, more targeted pool
    specific_tags = {"hispanic", "women-in-stem", "transfer", "uw-madison", "apia"}
    specificity_bonus = sum(5 for t in s.tags if t in specific_tags)
    base += specificity_bonus

    # Very large awards attract more applicants
    if s.amount_numeric >= 20000:
        base -= 15
    elif s.amount_numeric >= 10000:
        base -= 8
    elif s.amount_numeric <= 2000:
        base += 5

    # School-specific scholarships have smaller pools
    if "uw-madison" in s.tags:
        base += 10

    # Check manual overrides
    for key, val in COMPETITIVENESS_MAP.get(s.source, {}).items():
        if key.lower() in s.name.lower():
            base = val
            break

    return min(max(base, 10.0), 95.0)


def _win_probability(s: Scholarship) -> float:
    """
    0–100. Blends alignment and competitiveness.
    Formula: (alignment * 0.55) + (competitiveness * 0.35) + amount_bonus * 0.10
    """
    amount_bonus = min(s.amount_numeric / 1000, 10)   # up to 10 pts for higher awards
    prob = (
        s.alignment_score * 0.55
        + s.competitiveness_score * 0.35
        + amount_bonus * 0.10
    )
    return round(min(prob, 95.0), 1)


def _composite(s: Scholarship) -> float:
    """Final sort key. Weights win probability most, then amount."""
    amount_factor = min(s.amount_numeric / 50000 * 20, 20)  # max 20 pts
    return s.win_probability * 0.75 + amount_factor * 0.25
