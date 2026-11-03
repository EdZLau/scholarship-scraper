"""Fetch, cache, and extract scholarship detail-page information."""

import hashlib
import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from bs4 import BeautifulSoup
import requests

from data.models import Scholarship
from scrapers.base import HEADERS, fetch_soup

logger = logging.getLogger(__name__)
CACHE_MAX_AGE = timedelta(days=7)

MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)"
)
DATE_PATTERN = re.compile(
    rf"\b(?:{MONTH}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?"
    rf"|\d{{1,2}}[/-]\d{{1,2}}(?:[/-]\d{{2,4}})?"
    rf"|{MONTH}\.?\s+\d{{4}})\b",
    re.I,
)
DEADLINE_LABEL = re.compile(
    r"\b(?:application\s+)?(?:deadline|due date|applications due|apply by)\b",
    re.I,
)
AMOUNT_PATTERN = re.compile(
    r"\$\s*\d[\d,]*(?:\.\d{1,2})?(?:\s*(?:-|–|to)\s*\$\s*\d[\d,]*(?:\.\d{1,2})?)?"
)


class DetailPageEnricher:
    name = "details"

    def __init__(self, cache_dir: str = "logs/cache", refresh: bool = False):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.cache_dir = Path(cache_dir)
        self.today = date.today()
        self.refresh = refresh

    def enrich(self, scholarships: list[Scholarship]) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        for scholarship in scholarships:
            self._apply_listing_deadline(scholarship)

            if not scholarship.link:
                scholarship.needs_review = True
                scholarship.eligibility_note = "detail page unavailable"
                scholarship.eligibility_summary = scholarship.eligibility_note
                continue

            soup = self._load_page(scholarship.link)
            if soup is None:
                scholarship.needs_review = True
                scholarship.eligibility_note = "detail page unavailable"
                scholarship.eligibility_summary = scholarship.eligibility_note
                logger.warning(
                    "[details] %r detail page unavailable: %s",
                    scholarship.name,
                    scholarship.link,
                )
                continue

            eligibility = self._extract_eligibility(soup)
            if eligibility:
                if scholarship.eligibility_raw:
                    scholarship.eligibility_raw += "\n" + eligibility
                else:
                    scholarship.eligibility_raw = eligibility
            else:
                scholarship.needs_review = True

            deadline = self._extract_deadline(soup)
            if deadline:
                self._apply_deadline(scholarship, deadline)

            amount = self._extract_amount(soup)
            if amount:
                scholarship.amount = amount
                values = [
                    float(value.replace(",", ""))
                    for value in re.findall(r"\$\s*([\d,]+)", amount)
                ]
                scholarship.amount_numeric = max(values, default=scholarship.amount_numeric)

    def _load_page(self, url: str) -> BeautifulSoup | None:
        cache_key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        cache_path = self.cache_dir / f"{cache_key}.html"
        if cache_path.exists() and not self.refresh:
            try:
                age = datetime.now().timestamp() - cache_path.stat().st_mtime
            except OSError:
                logger.exception("[details] could not inspect cached page %s", cache_path)
            else:
                if age < CACHE_MAX_AGE.total_seconds():
                    try:
                        cached_html = cache_path.read_text(encoding="utf-8")
                    except OSError:
                        logger.exception("[details] could not read cached page %s", cache_path)
                    else:
                        return BeautifulSoup(cached_html, "html.parser")
                else:
                    logger.info("[details] cached page expired; refetching %s", url)
        elif cache_path.exists():
            logger.info("[details] refresh requested; refetching %s", url)

        soup = fetch_soup(self.session, self.name, url, retries=1)
        if soup is None:
            return None

        try:
            cache_path.write_text(str(soup), encoding="utf-8")
        except OSError:
            logger.exception("[details] could not cache detail page %s", url)
        return soup

    def _extract_eligibility(self, soup: BeautifulSoup) -> str:
        sections = []
        for heading in soup.find_all(re.compile(r"^h[1-6]$")):
            if not re.search(
                r"eligib|qualif|requirement|who can apply|applicant",
                heading.get_text(" ", strip=True),
                re.I,
            ):
                continue
            section = heading.find_parent("section")
            if section:
                section_text = section.get_text(" ", strip=True)
            else:
                sibling_text = []
                for sibling in heading.find_next_siblings():
                    if re.match(r"^h[1-6]$", sibling.name or ""):
                        break
                    sibling_text.append(sibling.get_text(" ", strip=True))
                section_text = " ".join(sibling_text)
                if not section_text and heading.parent:
                    section_text = heading.parent.get_text(" ", strip=True)
            if section_text:
                sections.append(section_text)
        return " ".join(dict.fromkeys(sections))[:5000]

    def _extract_deadline(self, soup: BeautifulSoup) -> date | None:
        for element in soup.find_all(attrs={"datetime": True}):
            itemprop = element.get("itemprop", "")
            if isinstance(itemprop, list):
                itemprop = " ".join(itemprop)
            if re.search(r"deadline|due|end", itemprop, re.I):
                parsed = self._parse_date(element.get("datetime", ""))
                if parsed:
                    return parsed

        for element in soup.find_all(
            ["time", "p", "li", "div", "span", "dt", "dd", "section", "article"]
        ):
            text = element.get_text(" ", strip=True)
            label = DEADLINE_LABEL.search(text)
            if not label:
                continue
            date_match = DATE_PATTERN.search(text[label.end():label.end() + 100])
            if date_match:
                parsed = self._parse_date(date_match.group(0))
                if parsed:
                    return parsed
            datetime_attr = element.get("datetime")
            if datetime_attr:
                parsed = self._parse_date(datetime_attr)
                if parsed:
                    return parsed
        return None

    def _apply_deadline(self, scholarship: Scholarship, deadline: date) -> None:
        scholarship.deadline = deadline.isoformat()
        scholarship.deadline_type = "exact"
        scholarship.due_date = deadline.strftime("%b %d, %Y")
        scholarship.due_date_sortable = deadline.isoformat()
        scholarship.due_within_30_days = (
            self.today <= deadline <= self.today + timedelta(days=30)
        )

    def _apply_listing_deadline(self, scholarship: Scholarship) -> None:
        value = scholarship.due_date.strip()
        exact_deadline = self._parse_date(value)
        if exact_deadline:
            self._apply_deadline(scholarship, exact_deadline)
            return

        month_match = re.search(
            rf"\b{MONTH}\b", value, re.I
        )
        if month_match:
            scholarship.deadline = value
            scholarship.deadline_type = "annual_month"
        else:
            scholarship.deadline = ""
            scholarship.deadline_type = "unknown"
        scholarship.due_within_30_days = False

    def _parse_date(self, value: str) -> date | None:
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).date()
        except ValueError:
            pass
        value = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", value.strip(), flags=re.I)
        for fmt in ("%B %d", "%b %d", "%m/%d"):
            try:
                parsed = datetime.strptime(
                    f"{value} {self.today.year}", f"{fmt} %Y"
                ).date()
            except ValueError:
                continue
            parsed = parsed.replace(year=self.today.year)
            if parsed < self.today:
                parsed = parsed.replace(year=self.today.year + 1)
            return parsed

        for fmt in (
            "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%m/%d/%Y", "%m/%d/%y",
            "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y",
        ):
            try:
                parsed = datetime.strptime(value, fmt).date()
            except ValueError:
                continue
            if "%Y" not in fmt:
                parsed = parsed.replace(year=self.today.year)
                if parsed < self.today:
                    parsed = parsed.replace(year=self.today.year + 1)
            return parsed
        return None

    def _extract_amount(self, soup: BeautifulSoup) -> str | None:
        for heading in soup.find_all(re.compile(r"^h[1-6]$")):
            if not re.search(r"award|amount|prize|scholarship value", heading.get_text(" ", strip=True), re.I):
                continue
            parent = heading.parent
            text = parent.get_text(" ", strip=True) if parent else ""
            match = AMOUNT_PATTERN.search(text)
            if match:
                return match.group(0)

        for element in soup.find_all(["p", "li", "div", "span"]):
            text = element.get_text(" ", strip=True)
            if re.search(r"award|amount|prize|worth|scholarship", text, re.I):
                match = AMOUNT_PATTERN.search(text)
                if match:
                    return match.group(0)
        return None
