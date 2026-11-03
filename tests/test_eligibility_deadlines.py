import hashlib
import os
from datetime import date, datetime, timedelta
from unittest.mock import Mock

import pytest
from bs4 import BeautifulSoup

import ranker.ranker as ranker
from data.models import Scholarship
from scrapers.detail_enricher import DetailPageEnricher


def scholarship(**overrides):
    values = {
        "name": "Example Scholarship",
        "link": "https://example.test/scholarship",
        "source": "test",
    }
    values.update(overrides)
    return Scholarship(**values)


@pytest.fixture
def eligibility_profile(monkeypatch):
    profile = {
  "gender": "Nonbinary",
"ethnicity": ["Pacific Islander"],
        "gpa": 3.7,
        "major": "Computer Science",
        "classification": "Junior (Transfer)",
        "transfer_from": "Previous University",
        "school": "University of Wisconsin-Madison",
        "state_residency": None,
        "us_citizen": None,
        "full_time": None,
        "first_gen": False,
        "financial_need": False,
        "stem_background": True,
    }
    monkeypatch.setattr(ranker, "PROFILE", profile)
    return profile


def test_gender_restriction_excludes_mismatch(eligibility_profile):
    item = scholarship(eligibility_raw="Scholarships are for male students only.")

    reasons, needs_review = ranker._eligibility_assessment(item)

    assert reasons == ["requires men"]
    assert needs_review is False


def test_ethnicity_restriction_excludes_mismatch(eligibility_profile):
    item = scholarship(eligibility_raw="Applicants must be of Asian heritage.")

    reasons, needs_review = ranker._eligibility_assessment(item)

    assert reasons
    assert "asian" in reasons[0]
    assert needs_review is False


def test_missing_citizenship_fact_needs_review(eligibility_profile):
    item = scholarship(eligibility_raw="Applicants must be U.S. citizens.")

    reasons, needs_review = ranker._eligibility_assessment(item)

    assert reasons == []
    assert needs_review is True


def test_deadline_parsing_and_annual_month_classification():
    enricher = DetailPageEnricher(cache_dir="unused-cache")
    enricher.today = date(2026, 11, 3)
    soup = BeautifulSoup(
        "<section><h2>Application Deadline</h2>"
        "<p>Apply by December 1, 2026.</p></section>",
        "html.parser",
    )
    exact = enricher._extract_deadline(soup)
    assert exact == date(2026, 12, 1)

    annual = scholarship(due_date="March (annual)")
    enricher._apply_listing_deadline(annual)
    assert annual.deadline_type == "annual_month"
    assert annual.deadline == "March (annual)"
    assert annual.due_within_30_days is False


def test_only_expired_exact_deadlines_are_excluded(monkeypatch, eligibility_profile):
    class FrozenDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 3)

    monkeypatch.setattr(ranker, "date", FrozenDate)
    expired_exact = scholarship(
        name="Expired exact",
        eligibility_raw="Any student may apply.",
        deadline="2026-11-02",
        deadline_type="exact",
    )
    old_annual = scholarship(
        name="Annual month",
        eligibility_raw="Any student may apply.",
        deadline="March (annual)",
        deadline_type="annual_month",
    )
    ranked = ranker.rank_scholarships([expired_exact, old_annual])

    assert [item.name for item in ranked] == ["Annual month"]
    assert old_annual.due_within_30_days is False


@pytest.mark.parametrize("refresh", [False, True])
def test_stale_or_forced_cache_refetches(tmp_path, monkeypatch, refresh):
    import scrapers.base

    monkeypatch.setattr(scrapers.base.time, "sleep", lambda _seconds: None)
    url = "https://example.test/scholarship"
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    cache_file = tmp_path / f"{key}.html"
    cache_file.write_text("<html>cached</html>", encoding="utf-8")
    timestamp = (datetime.now() - timedelta(days=8)).timestamp()
    if refresh:
        timestamp = datetime.now().timestamp()
    os.utime(cache_file, (timestamp, timestamp))

    enricher = DetailPageEnricher(cache_dir=str(tmp_path), refresh=refresh)
    response = Mock(text="<html>fresh</html>")
    response.raise_for_status.return_value = None
    enricher.session.get = Mock(return_value=response)

    soup = enricher._load_page(url)

    assert soup.get_text() == "fresh"
    enricher.session.get.assert_called_once_with(url, timeout=15)
