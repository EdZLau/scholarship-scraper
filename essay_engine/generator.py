"""
Essay generation engine.
Calls the Anthropic Claude API to generate a tailored sample essay
for each scholarship prompt, grounded in the user's real profile.
"""

import os
import time
import logging
import anthropic
from data.models import Scholarship
from config.profile import PROFILE

logger = logging.getLogger(__name__)

CLIENT = None  # lazy init


def _get_client() -> anthropic.Anthropic:
    global CLIENT
    if CLIENT is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY not set in environment.")
        CLIENT = anthropic.Anthropic(api_key=api_key)
    return CLIENT


def generate_essays(scholarships: list[Scholarship], delay: float = 1.5) -> list[Scholarship]:
    """
    Generates a sample essay for each scholarship that has an essay prompt.
    Skips scholarships where essay_prompt is empty.
    """
    client = _get_client()
    total = sum(1 for s in scholarships if s.essay_prompt)
    logger.info(f"[essay] generating essays for {total} scholarships...")

    for i, s in enumerate(scholarships):
        if not s.essay_prompt:
            s.sample_essay = "No essay prompt listed — check scholarship website."
            continue

        if s.sample_essay:  # already generated (e.g. resuming a run)
            continue

        try:
            s.sample_essay = _generate_single(client, s)
            logger.info(f"[essay] ({i+1}/{total}) done: {s.name[:50]}")
            time.sleep(delay)  # respect rate limits
        except Exception as e:
            logger.error(f"[essay] failed for {s.name}: {e}")
            s.sample_essay = f"[Generation failed: {e}]"

    return scholarships


def _generate_single(client: anthropic.Anthropic, s: Scholarship) -> str:
    p = PROFILE
    system_prompt = f"""You are an expert college scholarship essay coach.
Write a compelling, authentic 300-400 word scholarship essay.
Use first-person voice. Be specific — never generic.
Ground every claim in the applicant's real background below.
Do NOT start with "I" as the first word.
Do NOT use clichés like "passion" or "since I was a child".

APPLICANT PROFILE:
- Name: {p['name']}
- School: {p['school']} (transferred from {p['transfer_from']})
- Major: {p['major']}
- Prior background: {p['prior_major']}
- GPA: {p['gpa']}
- Relevant courses: {', '.join(p['relevant_coursework'])}
- Activities: {'; '.join(p['activities'])}
- Career goals: {p['career_goals']}
- Opening hook to use or adapt: "{p['essay_hook']}"

SCHOLARSHIP: {s.name}
ELIGIBILITY CONTEXT: {s.eligibility_summary or s.eligibility_raw}
"""

    user_prompt = f"""Write a 300-400 word essay responding to this prompt:

"{s.essay_prompt}"

Requirements:
1. Open with a specific scene, observation, or insight — not a biography recap.
2. Connect the applicant's biomedical + CS interdisciplinary background to the prompt.
3. Reference at least one real activity from their profile.
4. Close with how this scholarship specifically advances their goals.
5. Tone: confident, warm, specific. Avoid buzzwords."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=700,
        messages=[
            {"role": "user", "content": system_prompt + "\n\n" + user_prompt}
        ]
    )
    return message.content[0].text.strip()


def generate_eligibility_summary(scholarships: list[Scholarship]) -> list[Scholarship]:
    """
    Uses Claude to produce a clean 1-2 sentence eligibility summary
    from raw eligibility text, for the Google Sheet.
    """
    client = _get_client()
    for s in scholarships:
        if s.eligibility_summary or not s.eligibility_raw:
            continue
        try:
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=120,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Summarize this scholarship eligibility in 1-2 clear sentences, "
                        f"plain English, no jargon:\n\n{s.eligibility_raw}"
                    )
                }]
            )
            s.eligibility_summary = msg.content[0].text.strip()
            time.sleep(0.8)
        except Exception as e:
            s.eligibility_summary = s.eligibility_raw[:200]
            logger.warning(f"[essay] eligibility summary failed for {s.name}: {e}")
    return scholarships
