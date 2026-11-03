"""
Abstract base scraper. All source scrapers inherit from this.
"""

import logging
import time
import random
import requests
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from typing import List

from data.models import Scholarship

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_soup(
    session: requests.Session, name: str, url: str, retries: int = 3
) -> BeautifulSoup | None:
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            time.sleep(random.uniform(1.2, 2.5))
            return BeautifulSoup(resp.text, "html.parser")
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                logger.info(f"[{name}] skipping missing URL (404): {url}")
                return None
            logger.warning(f"[{name}] attempt {attempt+1} failed for {url}: {e}")
            time.sleep(2 ** attempt)
        except Exception as e:
            logger.warning(f"[{name}] attempt {attempt+1} failed for {url}: {e}")
            time.sleep(2 ** attempt)
    return None


class BaseScraper(ABC):
    name: str = "base"
    base_url: str = ""

    def __init__(self, session: requests.Session = None):
        self.session = session or requests.Session()
        self.session.headers.update(HEADERS)

    def get(self, url: str, retries: int = 3) -> BeautifulSoup | None:
        return fetch_soup(self.session, self.name, url, retries)

    @abstractmethod
    def scrape(self) -> List[Scholarship]:
        """Return a list of Scholarship objects."""
        ...

    def safe_text(self, element) -> str:
        return element.get_text(strip=True) if element else ""
