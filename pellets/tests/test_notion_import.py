"""Tests du parseur Notion + de l'import (sans appel API réel)."""

from __future__ import annotations

import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio

from app import db as db_mod
from app.services.notion_import import (
    ImportReport,
    NotionFournisseur,
    NotionLot,
    NotionMarque,
    NotionMouvement,
    _extract_date,
    _extract_number,
    _extract_select,
    _extract_text,
    import_fournisseurs,
    import_lots,
    import_marques,
    import_mouvements,
    parse_calendrier_pages,
    parse_pellets_pages,
)

# ----- Tests des extracteurs -----


def test_extract_text() -> None:
    assert _extract_text([{"plain_text": "Hello "}, {"plain_text": "world"}]) == "Hello world"
    assert _extract_text([]) == ""
    assert _extract_text(None) == ""


def test_extract_number() -> None:
    assert _extract_number({"type": "number", "number": 42.5}) == 42.5
    assert _extract_number({"type": "number", "number": None}) is None
    assert _extract_number(None) is None
    assert _extract_number({"type": "select"}) is None


def test_extract_select() -> None:
    assert _extract_select({"type": "select", "select": {"name": "Bois Rosa"}}) == "Bois Rosa"
    assert _extract_select({"type": "select", "select": None}) is None
    assert _extract_select(None) is None


def test_extract_date() -> None:
    assert _extract_date({"type": "date", "date": {"start": "2026-01-15"}}) == "2026-01-15"
    assert _extract_date(None) is None


# ----- Tests des parseurs -----


def test_parse_pellets_pages() -> None:
    pages = [
        {
            "id": "p1",
            "properties": {
                "Nom": {"title": [{"plain_text": "Piveteau 10kg"}]},
                "Fournisseur": {"type": "select", "select": {"name": "Bois Rosa"}},
                "Poids": {"type": "number", "number": 10.0},
            },
        },
        {
            "id": "p2",
            "properties": {
                "Nom": {"title": [{"plain_text": "Piveteau 15kg"}]},
                "Fournisseur": {"type": "select", "select": {"name": "Bois Rosa"}},
                "Poids": {"type": "number", "number": 15.0},
            },
        },
    ]
    marques = parse_pellets_pages(pages)
    assert len(marques) == 2
    assert marques[0].nom == "Piveteau 10kg"
    assert marques[0].fournisseur_nom == "Bois Rosa"
    assert marques[0].poids_kg_sac == 10.0


def test_parse_calendrier_pages_destockage() -> None:
    pages = [
        {
            "id": "c1",
            "properties": {
                "Date": {"type": "date", "date": {"start": "2025-11-17T17:58:00.000Z"}},
                "Ajout / Retrait Sac": {"type": "number", "number": -1},
                "Tag": {"type": "select", "select": {"name": "Chargement poêle"}},
                "Marque de Pellets": {"type": "relation", "relation": [{"id": "p1"}]},
            },
        },
    ]
    marque_index = {"p1": "Piveteau"}
    mouvements = parse_calendrier_pages(pages, marque_index)
    assert len(mouvements) == 1
    assert mouvements[0].type == "destockage"
    assert mouvements[0].sacs == -1
    assert mouvements[0].marque_nom == "Piveteau"


def test_parse_calendrier_pages_skip_reste() -> None:
    """Le tag 'Reste' doit être ignoré."""
    pages = [
        {
            "id": "c1",
            "properties": {
                "Date": {"type": "date", "date": {"start": "2025-11-17"}},
                "Ajout / Retrait Sac": {"type": "number", "number": 0},
                "Tag": {"type": "select", "select": {"name": "Reste"}},
            },
        },
    ]
    mouvements = parse_calendrier_pages(pages, {})
    assert mouvements == []


# ----- Tests d'injection (DB en tmp) -----


@pytest_asyncio.fixture
async def db() -> AsyncIterator[Path]:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "test.db"
        await db_mod.init_db(p)
        # On n'utilise pas seed() car on importe nos propres fournisseurs
        yield p


async def test_import_fournisseurs(db: Path) -> None:
    import aiosqlite

    report = ImportReport()
    async with aiosqlite.connect(db) as conn:
        conn.row_factory = aiosqlite.Row
        await import_fournisseurs(
            conn,
            [NotionFournisseur("Bois Rosa"), NotionFournisseur("Test")],
            report,
        )
        await conn.commit()
        cur = await conn.execute("SELECT nom FROM fournisseurs ORDER BY nom")
        rows = await cur.fetchall()
    assert {r["nom"] for r in rows} == {"Bois Rosa", "Test"}


async def test_import_marques_creates_with_fournisseur(db: Path) -> None:
    import aiosqlite

    # Pré-condition : fournisseur existe
    async with aiosqlite.connect(db) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("INSERT INTO fournisseurs (nom) VALUES ('Bois Rosa')")
        await conn.commit()

    report = ImportReport()
    async with aiosqlite.connect(db) as conn:
        conn.row_factory = aiosqlite.Row
        await import_marques(
            conn,
            [NotionMarque("Piveteau", "Bois Rosa", 15.0)],
            report,
        )
        await conn.commit()
        cur = await conn.execute("SELECT * FROM marques")
        rows = list(await cur.fetchall())
    assert len(rows) == 1
    assert rows[0]["nom"] == "Piveteau"
    assert rows[0]["fournisseur_id"] == 1
    assert report.marques_created == 1


async def test_import_marques_idempotent(db: Path) -> None:
    import aiosqlite

    async with aiosqlite.connect(db) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("INSERT INTO fournisseurs (nom) VALUES ('Bois Rosa')")
        await conn.commit()

    report1 = ImportReport()
    async with aiosqlite.connect(db) as conn:
        conn.row_factory = aiosqlite.Row
        await import_marques(conn, [NotionMarque("Piveteau", "Bois Rosa", 15.0)], report1)
        await conn.commit()
    report2 = ImportReport()
    async with aiosqlite.connect(db) as conn:
        conn.row_factory = aiosqlite.Row
        await import_marques(conn, [NotionMarque("Piveteau", "Bois Rosa", 15.0)], report2)
        await conn.commit()
    assert report1.marques_created == 1
    assert report2.marques_created == 0


async def test_import_lots_creates_mouvement(db: Path) -> None:
    import aiosqlite

    async with aiosqlite.connect(db) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("INSERT INTO fournisseurs (nom) VALUES ('Bois Rosa')")
        await conn.execute(
            "INSERT INTO marques (nom, fournisseur_id, poids_kg_sac) VALUES ('Piveteau', 1, 15.0)"
        )
        await conn.commit()

    report = ImportReport()
    async with aiosqlite.connect(db) as conn:
        conn.row_factory = aiosqlite.Row
        await import_lots(
            conn,
            [NotionLot("Piveteau", "Bois Rosa", "2026-01-15", 10, 15.0, 85.50)],
            report,
        )

    # Vérifier
    async with aiosqlite.connect(db) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM lots")
        lots = list(await cur.fetchall())
        cur = await conn.execute("SELECT * FROM mouvements")
        mvt = list(await cur.fetchall())
        cur = await conn.execute("SELECT * FROM v_stock")
        stock = await cur.fetchone()
    assert len(lots) == 1
    assert report.lots_created == 1
    # Le mouvement d'ajout doit aussi être créé
    assert len(mvt) == 1
    assert mvt[0]["type"] == "ajout"
    assert mvt[0]["poids_kg"] == 150.0
    assert stock["poids_kg_total"] == 150.0


async def test_import_lots_duplicate_skipped(db: Path) -> None:
    import aiosqlite

    async with aiosqlite.connect(db) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("INSERT INTO fournisseurs (nom) VALUES ('Bois Rosa')")
        await conn.execute(
            "INSERT INTO marques (nom, fournisseur_id, poids_kg_sac) VALUES ('Piveteau', 1, 15.0)"
        )
        await conn.commit()

    report = ImportReport()
    async with aiosqlite.connect(db) as conn:
        conn.row_factory = aiosqlite.Row
        # 1er import
        await import_lots(conn, [NotionLot("Piveteau", "Bois Rosa", "2026-01-15", 10, 15.0, 85.50)], report)
        # 2e import du même lot
        await import_lots(conn, [NotionLot("Piveteau", "Bois Rosa", "2026-01-15", 10, 15.0, 85.50)], report)

    assert report.lots_created == 1
    assert report.lots_skipped_duplicate == 1


async def test_import_mouvements_destockage(db: Path) -> None:
    import aiosqlite

    report = ImportReport()
    async with aiosqlite.connect(db) as conn:
        conn.row_factory = aiosqlite.Row
        await import_mouvements(
            conn,
            [
                NotionMouvement(
                    type="destockage",
                    date="2025-11-17T17:58:00",
                    sacs=-1,
                    poids_kg=-15.0,
                    notes="Bouton HA",
                ),
            ],
            report,
        )
        await conn.commit()
        cur = await conn.execute("SELECT * FROM v_stock")
        stock = await cur.fetchone()
    assert report.mouvements_created == 1
    # Pas de stock donc le mouvement fait passer le stock en négatif
    assert stock["poids_kg_total"] == -15.0
