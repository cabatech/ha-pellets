"""Connexion SQLite + initialisation du schéma.

Stratégie : pas d'Alembic (overkill). Le schéma est versionné dans
`SCHEMA_SQL` (idempotent via IF NOT EXISTS) et appliqué au lifespan.
On garde un `schema_version` dans une table meta pour pouvoir faire
des migrations manuelles plus tard si besoin.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from app.config import settings

_MEMORY = Path(":memory:")

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

SCHEMA_SQL = """
-- Table meta pour versionner le schéma
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fournisseurs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT UNIQUE NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS marques (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL,
    fournisseur_id INTEGER REFERENCES fournisseurs(id) ON DELETE SET NULL,
    poids_kg_sac REAL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (nom, fournisseur_id)
);

CREATE TABLE IF NOT EXISTS lots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    marque_id INTEGER NOT NULL REFERENCES marques(id) ON DELETE RESTRICT,
    date_achat TEXT NOT NULL,
    sacs INTEGER NOT NULL CHECK (sacs > 0),
    poids_sac_kg REAL NOT NULL CHECK (poids_sac_kg > 0),
    prix_total_eur REAL NOT NULL CHECK (prix_total_eur >= 0),
    fournisseur_id INTEGER REFERENCES fournisseurs(id) ON DELETE SET NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS mouvements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK(type IN ('destockage', 'ajout', 'inventaire', 'correction')),
    date TEXT NOT NULL,
    sacs INTEGER NOT NULL,
    poids_kg REAL NOT NULL,
    lot_id INTEGER REFERENCES lots(id) ON DELETE SET NULL,
    source TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_mouvements_date ON mouvements(date);
CREATE INDEX IF NOT EXISTS idx_mouvements_type ON mouvements(type);
CREATE INDEX IF NOT EXISTS idx_lots_marque ON lots(marque_id);
CREATE INDEX IF NOT EXISTS idx_lots_date_achat ON lots(date_achat);

-- Vues
CREATE VIEW IF NOT EXISTS v_stock AS
SELECT
    COALESCE(SUM(poids_kg), 0.0) AS poids_kg_total,
    COALESCE(SUM(sacs), 0) AS sacs_total
FROM mouvements;

CREATE VIEW IF NOT EXISTS v_conso_journaliere AS
SELECT
    date(date) AS jour,
    -SUM(CASE WHEN sacs < 0 THEN poids_kg ELSE 0 END) AS kg_consommes,
    -SUM(CASE WHEN sacs < 0 THEN sacs ELSE 0 END) AS sacs_consommes
FROM mouvements
WHERE type = 'destockage'
GROUP BY jour;

CREATE VIEW IF NOT EXISTS v_prix_moyen_achat AS
SELECT
    CASE WHEN SUM(sacs * poids_sac_kg) > 0
         THEN SUM(prix_total_eur) / SUM(sacs * poids_sac_kg)
         ELSE NULL
    END AS prix_moyen_kg
FROM lots;

CREATE VIEW IF NOT EXISTS v_cout_total AS
SELECT
    COALESCE(SUM(prix_total_eur), 0.0) AS cout_total_eur
FROM lots;
"""


async def get_connection(db_path: Path | None = None) -> aiosqlite.Connection:
    """Ouvre une connexion aiosqlite avec row_factory=Row.

    Args:
        db_path: chemin custom pour les tests. Si None, utilise settings.db_path.
    """
    path = db_path or settings.db_path
    if path != _MEMORY:
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(path)
    conn.row_factory = aiosqlite.Row
    # Activer les foreign keys (désactivées par défaut sur SQLite)
    await conn.execute("PRAGMA foreign_keys = ON")
    if path != _MEMORY:
        await conn.execute("PRAGMA journal_mode = WAL")
    return conn


@asynccontextmanager
async def connection(db_path: Path | None = None) -> AsyncIterator[aiosqlite.Connection]:
    """Context manager pour une connexion."""
    conn = await get_connection(db_path)
    try:
        yield conn
    finally:
        await conn.close()


async def init_db(db_path: Path | None = None) -> None:
    """Crée les tables et vues (idempotent). Écrit la version dans meta."""
    path = db_path or settings.db_path
    logger.info("init_db: %s", path)
    async with connection(db_path) as conn:
        await conn.executescript(SCHEMA_SQL)
        # Stocker la version du schéma
        await conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        await conn.commit()
    logger.info("init_db OK (schema v%s)", SCHEMA_VERSION)
