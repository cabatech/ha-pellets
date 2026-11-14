"""Tests du schéma DB et du seed."""

from __future__ import annotations

import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest_asyncio

from app import db as db_mod
from app.services.seed import seed


@pytest_asyncio.fixture
async def tmp_db() -> AsyncIterator[Path]:
    """DB SQLite temporaire pour les tests."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "test.db"
        await db_mod.init_db(p)
        await seed(p)
        yield p


async def test_init_creates_tables(tmp_db: Path) -> None:
    async with aiosqlite.connect(tmp_db) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {r["name"] for r in await cur.fetchall()}
    expected = {"meta", "fournisseurs", "marques", "lots", "mouvements"}
    assert expected.issubset(tables), f"Missing tables: {expected - tables}"


async def test_init_creates_views(tmp_db: Path) -> None:
    async with aiosqlite.connect(tmp_db) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name"
        )
        views = {r["name"] for r in await cur.fetchall()}
    assert {"v_stock", "v_conso_journaliere", "v_prix_moyen_achat", "v_cout_total"}.issubset(views)


async def test_init_is_idempotent(tmp_db: Path) -> None:
    """Deux init() successifs ne doivent pas planter."""
    await db_mod.init_db(tmp_db)
    await db_mod.init_db(tmp_db)


async def test_schema_version_recorded(tmp_db: Path) -> None:
    async with aiosqlite.connect(tmp_db) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT value FROM meta WHERE key='schema_version'")
        row = await cur.fetchone()
    assert row is not None
    assert row["value"] == str(db_mod.SCHEMA_VERSION)


async def test_seed_creates_fournisseurs(tmp_db: Path) -> None:
    async with aiosqlite.connect(tmp_db) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT nom FROM fournisseurs ORDER BY nom")
        noms = [r["nom"] for r in await cur.fetchall()]
    assert noms == ["Bois Rosa", "Butgaz", "Intermarché"]


async def test_seed_is_idempotent(tmp_db: Path) -> None:
    """Deux seed() successifs ne créent pas de doublons."""
    await seed(tmp_db)
    async with aiosqlite.connect(tmp_db) as conn:
        cur = await conn.execute("SELECT COUNT(*) AS c FROM fournisseurs")
        row = await cur.fetchone()
    assert row[0] == 3


async def test_v_stock_initially_zero(tmp_db: Path) -> None:
    async with aiosqlite.connect(tmp_db) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM v_stock")
        row = await cur.fetchone()
    assert row["poids_kg_total"] == 0.0
    assert row["sacs_total"] == 0


async def test_insert_mouvement_updates_stock(tmp_db: Path) -> None:
    """Insertion d'un destockage de 1 sac de 10kg doit baisser le stock (en fait ici on l'ajoute d'abord)."""
    async with aiosqlite.connect(tmp_db) as conn:
        conn.row_factory = aiosqlite.Row
        # D'abord on ajoute un sac (signe positif)
        await conn.execute(
            """INSERT INTO mouvements (type, date, sacs, poids_kg, source)
               VALUES ('ajout', '2026-01-15T10:00:00', 1, 10.0, 'web_ui')"""
        )
        await conn.commit()
        cur = await conn.execute("SELECT * FROM v_stock")
        row = await cur.fetchone()
    assert row["poids_kg_total"] == 10.0
    assert row["sacs_total"] == 1
