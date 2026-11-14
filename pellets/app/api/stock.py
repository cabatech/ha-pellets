"""API Stock & Stats (capteurs HA)."""

from __future__ import annotations

from datetime import date as date_t

from fastapi import APIRouter, Query

from app.db import connection
from app.schemas import (
    AutonomieJours,
    ConsoJour,
    CoutTotal,
    PrixMoyenAchat,
    Stock,
)
from app.services.calculations import (
    get_autonomie_jours,
    get_conso_journaliere,
    get_conso_periode,
    get_cout_total,
    get_prix_moyen_kg,
    get_stock,
)

router = APIRouter(prefix="/api", tags=["stock & stats"])


@router.get("/stock", response_model=Stock)
async def get_stock_endpoint() -> dict:
    """Stock actuel (poids total + nombre de sacs)."""
    async with connection() as conn:
        kg, sacs = await get_stock(conn)
    return {"poids_kg_total": kg, "sacs_total": sacs}


@router.get("/stats/conso", response_model=list[ConsoJour])
async def get_conso_endpoint(
    date_from: date_t | None = Query(default=None, description="Date min (ISO 8601)"),
    date_to: date_t | None = Query(default=None, description="Date max (ISO 8601)"),
) -> list[ConsoJour]:
    """Conso journalière sur la période (par défaut tout l'historique)."""
    async with connection() as conn:
        return await get_conso_journaliere(conn, date_from, date_to)


@router.get("/stats/conso/summary")
async def get_conso_summary(
    date_from: date_t | None = Query(default=None),
    date_to: date_t | None = Query(default=None),
) -> dict:
    """Conso totale sur la période : kg total, sacs total, jours."""
    async with connection() as conn:
        kg, sacs, jours = await get_conso_periode(conn, date_from, date_to)
    return {"kg_total": kg, "sacs_total": sacs, "jours": jours}


@router.get("/stats/cout", response_model=CoutTotal)
async def get_cout_endpoint() -> dict:
    """Coût total des achats."""
    async with connection() as conn:
        return {"cout_total_eur": await get_cout_total(conn)}


@router.get("/stats/prix-moyen", response_model=PrixMoyenAchat)
async def get_prix_moyen_endpoint() -> dict:
    """Prix moyen d'achat au kg."""
    async with connection() as conn:
        return {"prix_moyen_kg": await get_prix_moyen_kg(conn)}


@router.get("/stats/autonomie", response_model=AutonomieJours)
async def get_autonomie_endpoint() -> AutonomieJours:
    """Estimation du nombre de jours d'autonomie restante."""
    async with connection() as conn:
        return await get_autonomie_jours(conn)
