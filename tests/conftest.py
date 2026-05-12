"""Shared pytest fixtures."""
from __future__ import annotations

from pathlib import Path

import pytest

from ai_finops.db import Repository, get_session_factory, init_db
from ai_finops.services.cost_calculator import CostCalculator
from ai_finops.services.rate_card_service import RateCardService

REPO_ROOT = Path(__file__).resolve().parents[1]
RATE_CARD_DIR = REPO_ROOT / "config" / "rate_cards"


@pytest.fixture(scope="session")
def rate_card_service() -> RateCardService:
    return RateCardService(rate_card_dir=RATE_CARD_DIR, stale_days=365 * 10)


@pytest.fixture()
def calculator(rate_card_service: RateCardService) -> CostCalculator:
    return CostCalculator(rate_card_service)


@pytest.fixture()
def sqlite_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test.sqlite'}"


@pytest.fixture()
def repository(sqlite_url: str) -> Repository:
    init_db(sqlite_url)
    return Repository(get_session_factory(sqlite_url))
