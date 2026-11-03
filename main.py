"""
main.py — Scholarship Automation System
Run: python main.py

Flags:
  --no-essays       Skip essay generation (faster, no API cost)
  --no-sheets       Skip Google Sheets upload (dry run)
  --curated-only    Only use curated scholarships (skip web scraping)
  --limit N         Only process top N scholarships (useful for testing)
"""

import os
from dotenv import load_dotenv
load_dotenv()
import sys
import json
import logging
import argparse
import textwrap
from datetime import datetime
from pathlib import Path

# ── Make imports work from project root ─────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

# ── Logging setup ────────────────────────────────────────────────────────────
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/run.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ── Imports ───────────────────────────────────────────────────────────────────
from scrapers.bold_scraper import BoldScraper
from scrapers.curated_scraper import CuratedScraper
from scrapers.detail_enricher import DetailPageEnricher
from ranker.ranker import rank_scholarships
from essay_engine.generator import generate_essays, generate_eligibility_summary
from sheets.writer import write_to_sheet
from data.models import Scholarship


def parse_args():
    parser = argparse.ArgumentParser(description="Scholarship Automation System")
    parser.add_argument("--no-essays",     action="store_true")
    parser.add_argument("--no-sheets",     action="store_true")
    parser.add_argument("--curated-only",  action="store_true")
    parser.add_argument("--limit",         type=int, default=None)
    parser.add_argument("--refresh",      action="store_true")
    return parser.parse_args()


def deduplicate(scholarships: list[Scholarship]) -> list[Scholarship]:
    seen, unique = set(), []
    for s in scholarships:
        key = s.name.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(s)
    return unique


def save_json(scholarships: list[Scholarship], path: str = "logs/scholarships.json"):
    """Save results to JSON as a local backup."""
    Path(path).parent.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([s.to_dict() for s in scholarships], f, indent=2, default=str)
    logger.info(f"[main] saved {len(scholarships)} records → {path}")


def main():
    args = parse_args()
    Path("logs").mkdir(exist_ok=True)
    start = datetime.now()
    logger.info("=" * 60)
    logger.info("Scholarship Automation System — starting")
    logger.info(f"Flags: {vars(args)}")
    logger.info("=" * 60)

    # ── 1. Scrape ─────────────────────────────────────────────────────────────
    all_scholarships: list[Scholarship] = []

    scrapers = [CuratedScraper()]
    if not args.curated_only:
        scrapers.append(BoldScraper())
        logger.warning("[main] goingmerry scraper disabled (DNS resolution unavailable)")

    for scraper in scrapers:
        try:
            results = scraper.scrape()
            all_scholarships.extend(results)
            logger.info(f"[main] {scraper.name}: {len(results)} scholarships")
        except Exception as e:
            logger.error(f"[main] scraper {scraper.name} failed: {e}")

    # ── 2. Deduplicate ────────────────────────────────────────────────────────
    all_scholarships = deduplicate(all_scholarships)
    logger.info(f"[main] after dedup: {len(all_scholarships)} unique scholarships")

    # ── 3. Enrich detail pages ────────────────────────────────────────────────
    DetailPageEnricher(refresh=args.refresh).enrich(all_scholarships)

    # ── 4. Rank ───────────────────────────────────────────────────────────────
    all_scholarships = rank_scholarships(all_scholarships)

    if args.limit:
        all_scholarships = all_scholarships[: args.limit]
        logger.info(f"[main] limited to top {args.limit}")

    # ── 5. Eligibility summaries ──────────────────────────────────────────────
    if not args.no_essays:
        all_scholarships = generate_eligibility_summary(all_scholarships)

    # ── 6. Generate essays ────────────────────────────────────────────────────
    if not args.no_essays:
        all_scholarships = generate_essays(all_scholarships)
    else:
        logger.info("[main] skipping essay generation (--no-essays)")

    # ── 7. Save JSON backup ───────────────────────────────────────────────────
    save_json(all_scholarships)

    # ── 8. Write to Google Sheets ────────────────────────────────────────────
    if not args.no_sheets:
        try:
            url = write_to_sheet(all_scholarships)
            logger.info(f"[main] ✅ Google Sheet updated: {url}")
        except Exception as e:
            logger.error(f"[main] Google Sheets write failed: {e}")
            logger.info("[main] Data saved to logs/scholarships.json as backup.")
    else:
        logger.info("[main] skipping Google Sheets upload (--no-sheets)")

    elapsed = (datetime.now() - start).seconds
    logger.info(f"[main] done in {elapsed}s — {len(all_scholarships)} scholarships processed")

    # ── Print top 10 to console ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"TOP {min(10, len(all_scholarships))} SCHOLARSHIPS BY WIN PROBABILITY")
    print("=" * 60)
    for i, s in enumerate(all_scholarships[:10], 1):
        note = (
            s.eligibility_note or s.eligibility_summary or s.eligibility_raw
            or "Eligibility details unavailable"
        )
        note = textwrap.shorten(note, width=76, placeholder="...")
        review = "YES" if s.needs_review else "no"
        deadline = s.deadline or s.due_date
        due_soon = " | DUE WITHIN 30 DAYS" if s.due_within_30_days else ""
        print(
            f"{i:2}. {s.name[:42]:<42} {s.win_probability:5.1f}%  "
            f"{s.amount} | deadline={deadline} ({s.deadline_type}){due_soon} | "
            f"needs_review={review} | {note}"
        )
    print("=" * 60)


if __name__ == "__main__":
    main()
