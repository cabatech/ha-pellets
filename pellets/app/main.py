"""Module principal de l'application FastAPI."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import lots as api_lots
from app.api import mouvements as api_mouvements
from app.api import referentiels as api_ref
from app.api import stock as api_stock
from app.config import settings
from app.db import init_db
from app.services.seed import seed
from app.web import routes as web_routes

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialisation et nettoyage au démarrage/arrêt."""
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    await init_db()
    await seed()
    logger.info("pellets v%s démarré — DB: %s", __version__, settings.db_path)
    yield
    logger.info("pellets arrêt")


app = FastAPI(
    title="Gestion Stock Pellets",
    version=__version__,
    description="API de gestion de stock de pellets de bois",
    lifespan=lifespan,
)

# Static files (CSS, etc.)
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")

# Mount routers
app.include_router(api_ref.router)
app.include_router(api_lots.router)
app.include_router(api_mouvements.router)
app.include_router(api_stock.router)
app.include_router(web_routes.router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Healthcheck pour Docker / monitoring."""
    return {"status": "ok", "version": __version__}


@app.get("/api-info", include_in_schema=False)
async def api_info() -> dict[str, str]:
    """Info API + lien vers Swagger."""
    return {
        "service": "gestion-stock-pellets",
        "version": __version__,
        "phase": "4",
        "web_ui": "/",
        "api_docs": "/docs",
    }
