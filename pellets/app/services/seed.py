"""Seed initial des données de référence (fournisseurs, marques)."""

from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

from app.db import connection

logger = logging.getLogger(__name__)


# Données de seed basées sur l'historique Notion
SEED_FOURNISSEURS: list[dict[str, str | None]] = [
    {"nom": "Bois Rosa", "notes": "Fournisseur principal historique (Piveteau 10/15kg)"},
    {"nom": "Butgaz", "notes": None},
    {"nom": "Intermarché", "notes": "GMS"},
]


async def seed(db_path: Path | None = None) -> None:
    """Insère les fournisseurs de base s'ils n'existent pas déjà."""
    async with connection(db_path) as conn:
        for f in SEED_FOURNISSEURS:
            await conn.execute(
                "INSERT OR IGNORE INTO fournisseurs (nom, notes) VALUES (?, ?)",
                (f["nom"], f["notes"]),
            )
        await conn.commit()
        logger.info("seed OK (%d fournisseurs)", len(SEED_FOURNISSEURS))


async def get_fournisseurs(conn: aiosqlite.Connection) -> list[aiosqlite.Row]:
    """Liste tous les fournisseurs (triés par nom)."""
    cursor = await conn.execute("SELECT * FROM fournisseurs ORDER BY nom")
    return list(await cursor.fetchall())
