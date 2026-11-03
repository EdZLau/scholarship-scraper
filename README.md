Scholarship Scraper

A Python pipeline that finds scholarships, filters out the ones you can't apply to, ranks the rest by estimated win probability, and writes the results to a Google Sheet.

Features
Multi-source scraping: Bold.org plus a hand-curated list of high-value scholarships
Detail-page enrichment: fetches each scholarship's page to extract eligibility text, deadline and award amount (cached for 7 days)
Eligibility filter: excludes scholarships restricted by demographics, class standing, etc. that don't match your profile; ambiguous ones are flagged for review
Win-probability ranking: scores each scholarship against your profile and sorts the list
Deadline handling: classifies deadlines as exact, annual_month or unknown; expired and due-within-30-days logic applies only to exact dates
Google Sheets output: writes the ranked list, review flags and deadlines to a Scholarships tab
Optional essay drafting: generates essay drafts from your profile (skip with --no-essays)
Tests: pytest suite for the eligibility filter and deadline logic
Project structure
main.py              Pipeline entry point
config/              Applicant profile (profile.example.py is the template)
scrapers/            Bold.org, curated list, detail-page enricher
ranker/              Eligibility filter and win-probability scoring
sheets/              Google Sheets writer
essay_engine/        Essay draft generator
data/                Data models
tests/               pytest tests
logs/                Output JSON, cache and run logs (git-ignored)
Setup
Clone and install
bash
   git clone https://github.com/EdZLau/scholarship-scraper.git
   cd scholarship-scraper
   pip install -r requirements.txt
Create your profile
bash
   cp config/profile.example.py config/profile.py

Fill in your details. config/profile.py is git-ignored so your personal information stays local. Fields like us_citizen, full_time and state_residency should be set explicitly, since unknown values keep scholarships in the "needs review" bucket.

Google Sheets access
In Google Cloud, create a project and enable the Google Sheets and Google Drive APIs.
Create a service account and download its JSON key.
Save the key as credentials.json in the project root (git-ignored).
Environment variables Create a .env file in the project root (git-ignored) with the API key used by the essay generator. See essay_engine/generator.py for the variable name. Not needed if you always run with --no-essays.
Usage
bash
python main.py --no-essays
Flag	Effect
--no-essays	Skip essay generation
--no-sheets	Don't write to Google Sheets (JSON output only)
--curated-only	Use only the curated scholarship list
--limit N	Process at most N scholarships
--refresh	Ignore the detail-page cache and refetch

Output is saved to logs/scholarships.json as a backup, and to the Google Sheet when Sheets is enabled. The top 10 by win probability prints at the end of each run.

Tests
bash
python -m pytest -q
Notes and limitations
Win probabilities come from a heuristic scoring model, so treat them as relative rankings, not real odds.
Eligibility parsing depends on the text available on each scholarship page. Entries with missing or unclear criteria are flagged for manual review.
Scraper selectors and URLs depend on third-party sites and may need updating when those sites change.
Always confirm eligibility and deadlines on the official scholarship page before applying.
Security

credentials.json, .env and config/profile.py are git-ignored. Never commit them.
