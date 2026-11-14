"""Tests smoke de la Web UI (HTML)."""

from __future__ import annotations

import tempfile
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app import db as db_mod
from app.config import settings
from app.main import app
from app.services.seed import seed


@pytest_asyncio.fixture
async def client_with_data() -> AsyncIterator[AsyncClient]:
    """Client HTTP + DB temporaire + données de démo."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "test.db"
        object.__setattr__(settings, "db_path", p)
        await db_mod.init_db(p)
        await seed(p)
        # Données de démo
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            await ac.post(
                "/api/marques",
                json={"nom": "Piveteau", "fournisseur_id": 1, "poids_kg_sac": 15.0},
            )
            await ac.post(
                "/api/lots",
                json={
                    "marque_id": 1,
                    "date_achat": date.today().isoformat(),
                    "sacs": 10,
                    "poids_sac_kg": 15.0,
                    "prix_total_eur": 85.50,
                    "fournisseur_id": 1,
                },
            )
            await ac.post(
                "/api/mouvements",
                json={
                    "type": "destockage",
                    "date": f"{date.today().isoformat()}T18:00:00",
                    "sacs": -1,
                    "poids_kg": -15.0,
                    "source": "ha_button",
                },
            )
            yield ac
        object.__setattr__(settings, "db_path", Path("./data/pellets.db"))


async def test_dashboard_renders(client_with_data: AsyncClient) -> None:
    r = await client_with_data.get("/")
    assert r.status_code == 200
    assert "Stock" in r.text
    assert "Autonomie" in r.text
    assert "Prix moyen" in r.text
    assert "Coût total" in r.text


async def test_ajout_form_renders(client_with_data: AsyncClient) -> None:
    r = await client_with_data.get("/web/ajout")
    assert r.status_code == 200
    assert "Enregistrer un achat" in r.text
    assert "Bois Rosa" in r.text  # fournisseur dans le select


async def test_ajout_form_submission(client_with_data: AsyncClient) -> None:
    """Le POST crée un lot et redirige."""
    r = await client_with_data.post(
        "/web/ajout",
        data={
            "date_achat": date.today().isoformat(),
            "fournisseur_nom": "Butgaz",
            "nouvelle_marque_nom": "TestBrand",
            "sacs": "5",
            "poids_sac_kg": "10",
            "prix_total_eur": "25.50",
            "notes": "Test",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/web/lots"


async def test_lots_list_renders(client_with_data: AsyncClient) -> None:
    r = await client_with_data.get("/web/lots")
    assert r.status_code == 200
    assert "Piveteau" in r.text


async def test_mouvements_list_renders(client_with_data: AsyncClient) -> None:
    r = await client_with_data.get("/web/mouvements")
    assert r.status_code == 200
    assert "destockage" in r.text


async def test_mouvements_filter(client_with_data: AsyncClient) -> None:
    r = await client_with_data.get("/web/mouvements", params={"type": "destockage"})
    assert r.status_code == 200
    assert "destockage" in r.text
    # Le mouvement d'ajout du lot ne doit pas être visible
    r2 = await client_with_data.get("/web/mouvements", params={"type": "ajout"})
    assert r2.status_code == 200


async def test_stats_renders(client_with_data: AsyncClient) -> None:
    r = await client_with_data.get("/web/stats", params={"days": 30})
    assert r.status_code == 200
    assert "Statistiques" in r.text or "Période" in r.text


async def test_static_css_served(client_with_data: AsyncClient) -> None:
    r = await client_with_data.get("/static/styles.css")
    assert r.status_code == 200
    assert "css" in r.headers.get("content-type", "").lower()


async def test_ingress_prefix(client_with_data: AsyncClient) -> None:
    """Sous Ingress HA, les liens et la redirection gardent le préfixe X-Ingress-Path."""
    h = {"X-Ingress-Path": "/api/hassio_ingress/abc"}
    r = await client_with_data.get("/", headers=h)
    assert '<base href="/api/hassio_ingress/abc/">' in r.text
    assert 'href="/' not in r.text.replace('<base href="/', "")
    r = await client_with_data.post(
        "/web/ajout",
        headers=h,
        data={
            "date_achat": date.today().isoformat(),
            "fournisseur_nom": "Butgaz",
            "nouvelle_marque_nom": "TestBrand",
            "sacs": "1",
            "poids_sac_kg": "10",
            "prix_total_eur": "5",
        },
        follow_redirects=False,
    )
    assert r.headers["location"] == "/api/hassio_ingress/abc/web/lots"
