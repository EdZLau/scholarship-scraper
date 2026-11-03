"""
GoingMerry.com scholarship scraper.
Uses their public search pages for STEM / transfer / Hispanic scholarships.
"""

import re
import logging
from typing import List
from scrapers.base import BaseScraper
from data.models import Scholarship

logger = logging.getLogger(__name__)

SEARCH_URLS = [
    "https://www.goingmerry.com/scholarships/computer-science-scholarships/",
    "https://www.goingmerry.com/scholarships/hispanic-scholarships/",
    "https://www.goingmerry.com/scholarships/women-in-stem-scholarships/",
    "https://www.goingmerry.com/scholarships/transfer-student-scholarships/",
    "https://www.goingmerry.com/scholarships/artificial-intelligence-scholarships/",
]


class GoingMerryScraper(BaseScraper):
    name = "goingmerry"

    def scrape(self) -> List[Scholarship]:
        scholarships = []
        seen = set()

        for url in SEARCH_URLS:
            logger.info(f"[goingmerry] scraping: {url}")
            soup = self.get(url)
            if not soup:
                continue

            # GoingMerry renders cards in div.scholarship-card or similar
            cards = soup.select(
                "div[class*='scholarship'], article[class*='scholarship'], "
                "li[class*='scholarship']"
            )

            for card in cards:
                try:
                    link_tag = card.find("a", href=True)
                    if not link_tag:
                        continue
                    href = link_tag.get("href", "")
                    if not href.startswith("http"):
                        href = "https://www.goingmerry.com" + href
                    if href in seen:
                        continue
                    seen.add(href)

                    name = self.safe_text(card.find(["h2", "h3", "h4", "strong"]))
                    if not name:
                        name = self.safe_text(link_tag)
                    if len(name) < 5:
                        continue

                    amount_text = self.safe_text(
                        card.find(string=re.compile(r"\$[\d,]+|varies", re.I))
                    )
                    amount_num = self._parse_amount(amount_text)

                    due_tag = card.find(string=re.compile(r"\d{1,2}/\d{1,2}|\d{4}", re.I))
                    due_date = due_tag.strip() if due_tag else "See website"

                    scholarships.append(Scholarship(
                        name=name,
                        link=href,
                        source=self.name,
                        amount=amount_text or "Varies",
                        amount_numeric=amount_num,
                        due_date=due_date,
                        tags=self._infer_tags(name + " " + url),
                    ))
                except Exception as e:
                    logger.debug(f"[goingmerry] card error: {e}")

        logger.info(f"[goingmerry] found {len(scholarships)} scholarships")
        return scholarships

    def _parse_amount(self, text: str) -> float:
        match = re.search(r"\$([\d,]+)", text or "")
        return float(match.group(1).replace(",", "")) if match else 0.0

    def _infer_tags(self, text: str) -> list:
        text = text.lower()
        tags = []
        tag_map = {
            "hispanic": ["hispanic", "latino", "latina"],
            "women-in-stem": ["women", "woman", "female"],
            "transfer": ["transfer"],
            "stem": ["stem", "science", "engineering", "computer", "ai", "tech"],
            "biotech": ["bio", "neuro", "health"],
        }
        for tag, keywords in tag_map.items():
            if any(k in text for k in keywords):
                tags.append(tag)
        return tags
