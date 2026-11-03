"""
Bold.org scholarship scraper.
Searches for STEM, CS, transfer, and Hispanic scholarships.
"""

import re
import logging
from typing import List
from urllib.parse import urljoin, urlparse
from scrapers.base import BaseScraper
from data.models import Scholarship

logger = logging.getLogger(__name__)

SEARCH_QUERIES = [
    "computer-science",
    "stem-scholarships",
    "hispanic-latino",
    "transfer-students",
    "women-in-stem",
    "artificial-intelligence",
    "biomedical-engineering",
]


class BoldScraper(BaseScraper):
    name = "bold.org"
    base_url = "https://bold.org/scholarships"

    def scrape(self) -> List[Scholarship]:
        scholarships = []
        seen = set()
        dropped = 0

        for query in SEARCH_QUERIES:
            url = f"{self.base_url}/{query}/"
            logger.info(f"[bold.org] scraping: {url}")
            soup = self.get(url)
            if not soup:
                continue

            cards = soup.select("div[class*='ScholarshipCard'], article[class*='scholarship']")
            if not cards:
                # fallback: grab any card-like blocks
                cards = soup.select("a[href*='/scholarships/']")

            for card in cards:
                try:
                    link_tag = card if card.name == "a" else card.find("a", href=True)
                    if not link_tag:
                        dropped += 1
                        continue
                    href = urljoin("https://bold.org", link_tag.get("href", ""))
                    if href in seen:
                        continue
                    seen.add(href)

                    name = self.safe_text(
                        card.find(["h2", "h3", "h4"]) or link_tag
                    )
                    if not name or len(name) < 5 or not self._is_detail_url(href):
                        dropped += 1
                        continue

                    amount_el = card.find(
                        string=re.compile(r"\$\s*[\d,]+|full tuition|stipend", re.I)
                    )
                    amount_str = amount_el.strip() if amount_el else "Varies"
                    due_date = self._extract_deadline(card, name, amount_str)
                    has_award = bool(
                        re.search(r"\$\s*[\d,]+|\bfull tuition\b|\bstipend\b", amount_str, re.I)
                    )
                    if not has_award and due_date == "See website":
                        dropped += 1
                        continue

                    amount_num = self._parse_amount(amount_str)

                    scholarships.append(Scholarship(
                        name=name,
                        link=href,
                        source=self.name,
                        amount=amount_str,
                        amount_numeric=amount_num,
                        due_date=due_date,
                        tags=self._infer_tags(name + " " + query),
                    ))
                except Exception as e:
                    logger.debug(f"[bold.org] card parse error: {e}")

        logger.info("[bold.org] dropped %d non-scholarship/category results", dropped)
        logger.info(f"[bold.org] found {len(scholarships)} scholarships")
        return scholarships

    def _is_detail_url(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.hostname not in {"bold.org", "www.bold.org"}:
            return False

        parts = [part for part in parsed.path.lower().split("/") if part]
        if len(parts) != 2 or parts[0] != "scholarships":
            return False
        slug = parts[1]
        if (
            slug in {"scholarships", "next", "previous"}
            or slug.startswith(("by-major", "by-demographics", "by-year", "by-type"))
            or slug.startswith("scholarships-for-")
            or slug.endswith("-scholarships-list")
            or re.fullmatch(r"\d+", slug)
        ):
            return False
        return True

    def _extract_deadline(self, card, name: str, amount: str) -> str:
        text = card.get_text(" ", strip=True)
        for excluded in (name, amount):
            if excluded and excluded != "Varies":
                text = re.sub(re.escape(excluded), " ", text, flags=re.I)

        month = (
            r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
            r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
            r"Nov(?:ember)?|Dec(?:ember)?)"
        )
        patterns = (
            rf"\b{month}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?\b",
            rf"\b\d{{1,2}}/\d{{1,2}}(?:/\d{{2,4}})?\b",
            rf"\b{month}\.?\s+\d{{4}}\b",
            rf"\b(?:deadline|due date|apply by|applications? due)\s*[:\-]?\s*"
            rf"({month}(?:\s+\d{{1,2}})?(?:,?\s+\d{{4}})?|\d{{1,2}}/\d{{1,2}}(?:/\d{{2,4}})?)",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return match.group(1) if match.lastindex else match.group(0)
        return "See website"

    def _parse_amount(self, text: str) -> float:
        match = re.search(r"\$\s*([\d,]+)", text)
        if match:
            return float(match.group(1).replace(",", ""))
        return 0.0

    def _infer_tags(self, text: str) -> list:
        text = text.lower()
        tags = []
        if any(w in text for w in ["hispanic", "latino", "latina"]):
            tags.append("hispanic")
        if any(w in text for w in ["women", "woman", "female", "girl"]):
            tags.append("women-in-stem")
        if any(w in text for w in ["transfer"]):
            tags.append("transfer")
        if any(w in text for w in ["stem", "science", "engineering", "computer", "cs", "ai", "tech"]):
            tags.append("stem")
        if any(w in text for w in ["neuro", "biomedical", "bio"]):
            tags.append("biotech")
        return tags
