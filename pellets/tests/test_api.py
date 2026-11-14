"""Tests de l'API FastAPI."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app import db as db_mod
from app.config import settings
from app.main import app
from app.services.seed import seed


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Client HTTP + DB temporaire."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "test.db"
        # On force le path via monkeypatch sur le singleton settings
        original = settings.db_path
        object.__setattr__(settings, "db_path", p)
        await db_mod.init_db(p)
        await seed(p)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                yield ac
        finally:
            object.__setattr__(settings, "db_path", original)


# ----- Health -----


async def test_health(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ----- Fournisseurs -----


async def test_list_fournisseurs_empty(client: AsyncClient) -> None:
    r = await client.get("/api/fournisseurs")
    assert r.status_code == 200
    # Le seed a déjà 3 fournisseurs
    assert len(r.json()) == 3
    assert {f["nom"] for f in r.json()} == {"Bois Rosa", "Butgaz", "Intermarché"}


async def test_create_fournisseur(client: AsyncClient) -> None:
    r = await client.post("/api/fournisseurs", json={"nom": "Leroy Merlin", "notes": "GMS"})
    assert r.status_code == 201
    assert r.json()["nom"] == "Leroy Merlin"
    assert r.json()["id"] > 0


async def test_create_duplicate_fournisseur(client: AsyncClient) -> None:
    r = await client.post("/api/fournisseurs", json={"nom": "Bois Rosa"})
    assert r.status_code == 409


# ----- Stock initial -----


async def test_stock_initial_zero(client: AsyncClient) -> None:
    r = await client.get("/api/stock")
    assert r.status_code == 200
    data = r.json()
    assert data["poids_kg_total"] == 0.0
    assert data["sacs_total"] == 0


# ----- Mouvements -----


async def test_create_destockage(client: AsyncClient) -> None:
    """Crée un destockage de 1 sac de 10kg (scénario bouton HA)."""
    r = await client.post(
        "/api/mouvements",
        json={
            "type": "destockage",
            "date": "2026-01-15T18:30:00",
            "sacs": -1,
            "poids_kg": -10.0,
            "source": "ha_button",
            "notes": "Test bouton HA",
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["sacs"] == -1
    assert data["source"] == "ha_button"
    # Pas d'assertion sur le stock : sans achat préalable, le stock peut devenir
    # négatif (l'utilisateur ajoutera l'achat plus tard). Le système autorise ça.


async def test_create_lot_and_ajout(client: AsyncClient) -> None:
    """Scénario : on achète 10 sacs de 15kg à 85.50€ chez Bois Rosa (Piveteau)."""
    # Créer la marque Piveteau chez Bois Rosa (id=1 du seed)
    r = await client.post(
        "/api/marques",
        json={"nom": "Piveteau", "fournisseur_id": 1, "poids_kg_sac": 15.0},
    )
    assert r.status_code == 201
    marque_id = r.json()["id"]

    # Créer le lot
    r = await client.post(
        "/api/lots",
        json={
            "marque_id": marque_id,
            "date_achat": "2026-01-15",
            "sacs": 10,
            "poids_sac_kg": 15.0,
            "prix_total_eur": 85.50,
            "fournisseur_id": 1,
        },
    )
    assert r.status_code == 201

    # Le lot crée automatiquement un mouvement d'ajout
    r = await client.get("/api/stock")
    assert r.json()["poids_kg_total"] == 150.0  # 10 * 15
    assert r.json()["sacs_total"] == 10

    # Vérifier le prix moyen
    r = await client.get("/api/stats/prix-moyen")
    assert r.json()["prix_moyen_kg"] == pytest.approx(85.5 / 150, rel=1e-3)


async def test_create_lot_with_new_marque_and_fournisseur(client: AsyncClient) -> None:
    """Création d'un lot avec marque et fournisseur créés à la volée."""
    r = await client.post(
        "/api/lots",
        json={
            "marque_id": None,
            "nouveau_fournisseur": {"nom": "Nouveau Fournisseur", "notes": "Test"},
            "nouvelle_marque": {
                "nom": "Nouvelle Marque",
                "fournisseur_id": None,
                "poids_kg_sac": 10.0,
            },
            "date_achat": "2026-02-01",
            "sacs": 5,
            "poids_sac_kg": 10.0,
            "prix_total_eur": 30.0,
        },
    )
    assert r.status_code == 201
    assert r.json()["id"] > 0

    # Vérifier que le fournisseur a été créé
    r = await client.get("/api/fournisseurs")
    noms = {f["nom"] for f in r.json()}
    assert "Nouveau Fournisseur" in noms


async def test_destockage_decreases_stock(client: AsyncClient) -> None:
    """Scénario complet : achat 10 sacs de 15kg + 3 destockages."""
    # Marque + lot
    r = await client.post(
        "/api/marques",
        json={"nom": "Piveteau", "fournisseur_id": 1, "poids_kg_sac": 15.0},
    )
    marque_id = r.json()["id"]
    r = await client.post(
        "/api/lots",
        json={
            "marque_id": marque_id,
            "date_achat": date.today().isoformat(),
            "sacs": 10,
            "poids_sac_kg": 15.0,
            "prix_total_eur": 85.50,
            "fournisseur_id": 1,
        },
    )

    # 3 destockages d'1 sac sur les 3 derniers jours
    today = date.today()
    for i in range(3):
        d = today - timedelta(days=2 - i)
        r = await client.post(
            "/api/mouvements",
            json={
                "type": "destockage",
                "date": f"{d.isoformat()}T18:00:00",
                "sacs": -1,
                "poids_kg": -15.0,
                "source": "ha_button",
            },
        )
        assert r.status_code == 201

    # Stock = 7 sacs = 105 kg
    r = await client.get("/api/stock")
    assert r.json()["poids_kg_total"] == 105.0
    assert r.json()["sacs_total"] == 7

    # Autonomie : 7 sacs de 15kg = 105kg, 3 destockages sur 3 jours = 15kg/j
    # 105 / 15 = 7 jours
    r = await client.get("/api/stats/autonomie")
    data = r.json()
    assert data["jours"] == pytest.approx(7.0, rel=1e-1)


async def test_conso_journaliere(client: AsyncClient) -> None:
    """v_conso_journaliere doit être calculée correctement."""
    # Créer marque + lot pour avoir du stock
    r = await client.post(
        "/api/marques",
        json={"nom": "Piveteau", "fournisseur_id": 1, "poids_kg_sac": 10.0},
    )
    marque_id = r.json()["id"]
    r = await client.post(
        "/api/lots",
        json={
            "marque_id": marque_id,
            "date_achat": (date.today() - timedelta(days=20)).isoformat(),
            "sacs": 20,
            "poids_sac_kg": 10.0,
            "prix_total_eur": 100.0,
            "fournisseur_id": 1,
        },
    )

    # 5 destockages sur 5 jours récents
    base = date.today() - timedelta(days=4)
    for i in range(5):
        d = base + timedelta(days=i)
        await client.post(
            "/api/mouvements",
            json={
                "type": "destockage",
                "date": f"{d.isoformat()}T18:00:00",
                "sacs": -1,
                "poids_kg": -10.0,
                "source": "ha_button",
            },
        )

    r = await client.get("/api/stats/conso")
    data = r.json()
    assert len(data) == 5
    assert all(d["kg_consommes"] == 10.0 for d in data)


async def test_list_mouvements_with_filters(client: AsyncClient) -> None:
    """Filtres sur type, date_from, date_to."""
    r = await client.post(
        "/api/marques",
        json={"nom": "Piveteau", "fournisseur_id": 1, "poids_kg_sac": 10.0},
    )
    marque_id = r.json()["id"]
    r = await client.post(
        "/api/lots",
        json={
            "marque_id": marque_id,
            "date_achat": date.today().isoformat(),
            "sacs": 10,
            "poids_sac_kg": 10.0,
            "prix_total_eur": 50.0,
            "fournisseur_id": 1,
        },
    )

    # 2 destockages
    today = date.today()
    for i in [5, 10]:
        d = today - timedelta(days=i)
        await client.post(
            "/api/mouvements",
            json={
                "type": "destockage",
                "date": f"{d.isoformat()}T18:00:00",
                "sacs": -1,
                "poids_kg": -10.0,
                "source": "ha_button",
            },
        )

    # Filtre par type
    r = await client.get("/api/mouvements", params={"type": "destockage"})
    destockages = r.json()
    assert len(destockages) == 2

    # Filtre par date + type (le mouvement d'ajout du lot est aujourd'hui)
    r = await client.get(
        "/api/mouvements",
        params={
            "date_from": (today - timedelta(days=7)).isoformat(),
            "type": "destockage",
        },
    )
    assert len(r.json()) == 1

    # Filtre par source
    r = await client.get("/api/mouvements", params={"type": "destockage", "limit": 10})
    assert all(m["source"] == "ha_button" for m in r.json())


async def test_delete_mouvement(client: AsyncClient) -> None:
    """Suppression d'un mouvement (correction)."""
    r = await client.post(
        "/api/mouvements",
        json={
            "type": "destockage",
            "date": "2026-01-15T18:00:00",
            "sacs": -1,
            "poids_kg": -10.0,
            "source": "ha_button",
        },
    )
    mid = r.json()["id"]

    r = await client.delete(f"/api/mouvements/{mid}")
    assert r.status_code == 204

    r = await client.delete(f"/api/mouvements/{mid}")
    assert r.status_code == 404
