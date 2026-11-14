"""Routes Web UI (HTML)."""

from __future__ import annotations

import contextlib
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db import connection
from app.schemas import FournisseurCreate, LotCreate, MarqueCreate
from app.services.calculations import (
    get_autonomie_jours,
    get_conso_journaliere,
    get_cout_total,
    get_prix_moyen_kg,
    get_stock,
)

router = APIRouter(tags=["web ui"])

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ----- Pages -----


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Dashboard principal : stock + KPIs + graphique conso 30j."""
    today = date.today()
    thirty_days_ago = today - timedelta(days=30)

    async with connection() as conn:
        stock_kg, stock_sacs = await get_stock(conn)
        conso_30j = await get_conso_journaliere(conn, date_from=thirty_days_ago)
        autonomie = await get_autonomie_jours(conn)
        prix_moyen = await get_prix_moyen_kg(conn)
        cout_total = await get_cout_total(conn)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "stock_kg": stock_kg,
            "stock_sacs": stock_sacs,
            "autonomie": autonomie,
            "prix_moyen_kg": prix_moyen,
            "cout_total_eur": cout_total,
            "conso_30j": conso_30j,
            "today": today.isoformat(),
        },
    )


@router.get("/web/ajout", response_class=HTMLResponse)
async def ajout_form(request: Request) -> HTMLResponse:
    """Formulaire d'ajout d'un lot (achat)."""
    async with connection() as conn:
        fournisseurs = list(await (await conn.execute("SELECT * FROM fournisseurs ORDER BY nom")).fetchall())
        marques = list(
            await (
                await conn.execute(
                    """SELECT m.*, f.nom AS fournisseur_nom
                       FROM marques m LEFT JOIN fournisseurs f ON m.fournisseur_id = f.id
                       ORDER BY m.nom"""
                )
            ).fetchall()
        )
    return templates.TemplateResponse(
        request,
        "ajout.html",
        {"fournisseurs": fournisseurs, "marques": marques, "today": date.today().isoformat()},
    )


@router.post("/web/ajout")
async def ajout_submit(
    request: Request,
    date_achat: str = Form(...),
    fournisseur_nom: str = Form(""),
    nouvelle_marque_nom: str = Form(""),
    marque_id: str = Form(""),
    sacs: int = Form(...),
    poids_sac_kg: float = Form(...),
    prix_total_eur: float = Form(...),
    notes: str = Form(""),
) -> RedirectResponse:
    """Soumission du formulaire d'achat. Crée le lot via l'API interne."""
    # Validation basique
    if sacs <= 0 or poids_sac_kg <= 0 or prix_total_eur < 0:
        raise HTTPException(status_code=400, detail="Valeurs invalides")

    payload = LotCreate(
        marque_id=int(marque_id) if marque_id else None,
        date_achat=date.fromisoformat(date_achat),
        sacs=sacs,
        poids_sac_kg=poids_sac_kg,
        prix_total_eur=prix_total_eur,
        fournisseur_id=None,
        notes=notes or None,
        nouveau_fournisseur=FournisseurCreate(nom=fournisseur_nom) if fournisseur_nom else None,
        nouvelle_marque=MarqueCreate(
            nom=nouvelle_marque_nom,
            poids_kg_sac=poids_sac_kg,
        ) if nouvelle_marque_nom else None,
    )

    # On appelle directement la logique d'API
    from app.api.lots import create_lot

    await create_lot(payload)
    return RedirectResponse(url=request.headers.get("x-ingress-path", "") + "/web/lots", status_code=303)


@router.get("/web/lots", response_class=HTMLResponse)
async def lots_list(request: Request) -> HTMLResponse:
    """Liste des lots achetés."""
    async with connection() as conn:
        cur = await conn.execute(
            """
            SELECT l.*, m.nom AS marque_nom, f.nom AS fournisseur_nom,
                   (SELECT COUNT(*) FROM mouvements WHERE lot_id = l.id) AS nb_mouvements
            FROM lots l
            LEFT JOIN marques m ON l.marque_id = m.id
            LEFT JOIN fournisseurs f ON l.fournisseur_id = f.id
            ORDER BY l.date_achat DESC
            LIMIT 100
            """
        )
        lots = [dict(r) for r in await cur.fetchall()]

    return templates.TemplateResponse(
        request,
        "lots.html",
        {"lots": lots},
    )


@router.get("/web/mouvements", response_class=HTMLResponse)
async def mouvements_list(
    request: Request,
    type: str = "",
    limit: int = 100,
) -> HTMLResponse:
    """Historique des mouvements."""
    from app.schemas import MouvementType

    type_filter = None
    if type:
        with contextlib.suppress(ValueError):
            type_filter = MouvementType(type)

    query = """
        SELECT m.*, mk.nom AS marque_nom, f.nom AS fournisseur_nom
        FROM mouvements m
        LEFT JOIN lots l ON m.lot_id = l.id
        LEFT JOIN marques mk ON l.marque_id = mk.id
        LEFT JOIN fournisseurs f ON l.fournisseur_id = f.id
    """
    params: list = []
    if type_filter is not None:
        query += " WHERE m.type = ?"
        params.append(type_filter.value)
    query += " ORDER BY m.date DESC LIMIT ?"
    params.append(limit)

    async with connection() as conn:
        mouvements = [dict(r) for r in await (await conn.execute(query, params)).fetchall()]

    return templates.TemplateResponse(
        request,
        "mouvements.html",
        {
            "mouvements": mouvements,
            "type_filter": type,
            "limit": limit,
            "MouvementType": MouvementType,
        },
    )


@router.get("/web/stats", response_class=HTMLResponse)
async def stats_page(
    request: Request,
    days: int = 90,
) -> HTMLResponse:
    """Page stats : graphique conso, comparaison conso/°C (placeholder), etc."""
    days = max(7, min(days, 730))  # bornage 7j..2ans
    today = date.today()
    since = today - timedelta(days=days)

    async with connection() as conn:
        conso = await get_conso_journaliere(conn, date_from=since)
        stock_kg, stock_sacs = await get_stock(conn)
        prix_moyen = await get_prix_moyen_kg(conn)

    # Préparer les données pour Chart.js
    labels = [c.jour.isoformat() for c in conso]
    kg = [c.kg_consommes for c in conso]
    sacs = [c.sacs_consommes for c in conso]
    cumul_kg = []
    cumul = 0.0
    for k in kg:
        cumul += k
        cumul_kg.append(round(cumul, 2))

    total_kg = sum(kg)
    total_sacs = sum(sacs)
    jours_conso = len(conso)

    return templates.TemplateResponse(
        request,
        "stats.html",
        {
            "labels": labels,
            "kg": kg,
            "sacs": sacs,
            "cumul_kg": cumul_kg,
            "stock_kg": stock_kg,
            "stock_sacs": stock_sacs,
            "prix_moyen_kg": prix_moyen,
            "total_kg": total_kg,
            "total_sacs": total_sacs,
            "jours_conso": jours_conso,
            "days": days,
        },
    )
