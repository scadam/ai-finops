"""Shared pytest fixtures."""
from __future__ import annotations

from pathlib import Path

import pytest

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
