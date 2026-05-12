"""FastAPI application entrypoint.

Run locally with::

    uvicorn ai_finops.main:app --reload

In Azure App Service the start command is provided in ``scripts/deploy.sh``.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .config import get_settings
from .db import Repository, get_session_factory, init_db
from .modeler.scenario_comparison import ScenarioComparison
from .optimisation.recommender import OptimisationRecommender
from .services.cost_calculator import CostCalculator
from .services.rate_card_service import RateCardService

logger = logging.getLogger("ai_finops")


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    app = FastAPI(
        title="AI FinOps",
        version="0.1.0",
        description="Enterprise FinOps for the Microsoft AI Frontier Platform.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    rate_card_service = RateCardService(
        rate_card_dir=settings.rate_card_dir,
        stale_days=settings.rate_card_stale_days,
    )
    cost_calculator = CostCalculator(rate_card_service)
    scenario_comparison = ScenarioComparison(cost_calculator)
    optimisation_recommender = OptimisationRecommender(rate_card_service)

    init_db(settings.database_url)
    repository = Repository(get_session_factory(settings.database_url))

    app.state.settings = settings
    app.state.rate_card_service = rate_card_service
    app.state.cost_calculator = cost_calculator
    app.state.scenario_comparison = scenario_comparison
    app.state.optimisation_recommender = optimisation_recommender
    app.state.repository = repository

    app.include_router(router)

    @app.get("/", tags=["meta"])
    def root() -> dict[str, str]:
        return {
            "name": "ai-finops",
            "version": app.version,
            "docs": "/docs",
            "health": "/api/v1/health",
        }

    return app


app = create_app()
