"""Import des données depuis Notion (one-shot).

Stratégie : on lit les 2 DBs Notion (Pellets et Calendrier Pellets) via
l'API REST Notion, on convertit en modèles locaux, et on injecte dans
SQLite. L'opération est idempotente (basée sur les dates + sacs).

Données Notion vues :
- DB Pellets : marques (Fournisseur, Poids, Prix, Date du prix)
- DB Calendrier Pellets : mouvements (date, marque, sacs ±, tag)

On retrouve l'historique par tag "Achat" (mouvement positif avec lot) et
"Chargement poêle" (mouvement négatif de destockage).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import aiosqlite
import httpx

from app.db import connection

logger = logging.getLogger(__name__)

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"  # stable


@dataclass
class NotionFournisseur:
    nom: str


@dataclass
class NotionMarque:
    nom: str
    fournisseur_nom: str
    poids_kg_sac: float | None = None


@dataclass
class NotionLot:
    marque_nom: str
    fournisseur_nom: str
    date_achat: str  # ISO 8601 date
    sacs: int
    poids_sac_kg: float
    prix_total_eur: float


@dataclass
class NotionMouvement:
    """Mouvement de stock (depuis Calendrier Pellets)."""

    type: str  # 'destockage' | 'ajout'
    date: str  # ISO 8601 datetime
    sacs: int  # peut être négatif
    poids_kg: float
    marque_nom: str | None = None
    notes: str | None = None


@dataclass
class ImportReport:
    """Rapport d'import (nb créés / ignorés / erreurs)."""

    fournisseurs_created: int = 0
    marques_created: int = 0
    lots_created: int = 0
    lots_skipped_duplicate: int = 0
    mouvements_created: int = 0
    erreurs: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Fournisseurs créés: {self.fournisseurs_created}\n"
            f"Marques créées: {self.marques_created}\n"
            f"Lots créés: {self.lots_created} (skipped doublons: {self.lots_skipped_duplicate})\n"
            f"Mouvements créés: {self.mouvements_created}\n"
            f"Erreurs: {len(self.erreurs)}"
        )


# ----- Lecture depuis l'API Notion -----


async def _notion_query_database(
    database_id: str,
    token: str,
) -> list[dict]:
    """Query tous les enregistrements d'une DB Notion (pagination auto)."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    results: list[dict] = []
    cursor: str | None = None

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            payload: dict = {"page_size": 100}
            if cursor:
                payload["start_cursor"] = cursor
            r = await client.post(
                f"{NOTION_API_BASE}/databases/{database_id}/query",
                headers=headers,
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            results.extend(data.get("results", []))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")

    return results


def _extract_text(rich_text: list[dict] | None) -> str:
    """Concatène les plain_text d'un champ rich_text Notion."""
    if not rich_text:
        return ""
    return "".join(t.get("plain_text", "") for t in rich_text)


def _extract_number(prop: dict | None) -> float | None:
    if not prop:
        return None
    if prop.get("type") == "number":
        return prop.get("number")
    return None


def _extract_select(prop: dict | None) -> str | None:
    if not prop:
        return None
    if prop.get("type") == "select":
        sel = prop.get("select")
        return sel.get("name") if sel else None
    return None


def _extract_date(prop: dict | None) -> str | None:
    if not prop:
        return None
    if prop.get("type") == "date":
        d = prop.get("date")
        return d.get("start") if d else None
    return None


def _extract_relation(prop: dict | None) -> list[str]:
    """Retourne la liste des page IDs des relations."""
    if not prop:
        return []
    if prop.get("type") == "relation":
        return [r.get("id") for r in prop.get("relation", []) if r.get("id")]
    return []


def _extract_relation_titles(prop: dict | None) -> list[str]:
    """Pour lire les titres des relations, on les cherche dans les pages de résultats."""
    return []  # résolu côté appelant si nécessaire


def parse_pellets_pages(pages: list[dict]) -> list[NotionMarque]:
    """Parse les pages de la DB 'Pellets' en NotionMarque."""
    marques: list[NotionMarque] = []
    for page in pages:
        props = page.get("properties", {})
        nom = _extract_text(props.get("Nom", {}).get("title"))
        fournisseur = _extract_select(props.get("Fournisseur")) or "?"
        poids = _extract_number(props.get("Poids"))
        marques.append(NotionMarque(nom=nom, fournisseur_nom=fournisseur, poids_kg_sac=poids))
    return marques


def parse_calendrier_pages(
    pages: list[dict],
    marque_index: dict[str, str],  # page_id -> nom de marque
) -> list[NotionMouvement]:
    """Parse les pages de la DB 'Calendrier Pellets' en NotionMouvement.

    Marque_index est un dict {page_id: nom_marque} construit depuis la DB Pellets
    (relation dans Calendrier pointe vers Pellets).
    """
    mouvements: list[NotionMouvement] = []
    for page in pages:
        props = page.get("properties", {})
        date_iso = _extract_date(props.get("Date"))
        sacs = _extract_number(props.get("Ajout / Retrait Sac")) or 0
        tag = _extract_select(props.get("Tag")) or ""
        # Relations marque
        rels = _extract_relation(props.get("Marque de Pellets"))
        marque_nom = marque_index.get(rels[0]) if rels else None

        # Tag -> type local
        if tag == "Chargement poêle":
            mtype = "destockage"
            sacs_int = int(sacs) if sacs else 0
        elif tag == "Achat":
            mtype = "ajout"
            sacs_int = int(sacs) if sacs else 0
        else:
            # "Reste" = ajustement inventaire, on skip
            continue

        # poids : calculé depuis le rollup (pas accessible via API simple).
        # On le laisse à None et on le recalcule via une 2e passe si besoin.
        poids = sacs_int * 15.0  # heuristique par défaut, sera raffiné

        if not date_iso:
            continue

        mouvements.append(
            NotionMouvement(
                type=mtype,
                date=date_iso,
                sacs=sacs_int,
                poids_kg=poids,
                marque_nom=marque_nom,
                notes=f"Importé depuis Notion ({tag})",
            )
        )
    return mouvements


# ----- Injection dans SQLite -----


async def import_fournisseurs(
    conn: aiosqlite.Connection,
    fournisseurs: list[NotionFournisseur],
    report: ImportReport,
) -> None:
    for f in fournisseurs:
        try:
            await conn.execute(
                "INSERT OR IGNORE INTO fournisseurs (nom) VALUES (?)",
                (f.nom,),
            )
            if (await conn.execute("SELECT id FROM fournisseurs WHERE nom = ?", (f.nom,))).fetchone():
                pass
            # rowcount n'est pas dispo sur aiosqlite, on ne peut pas savoir si créé
            # ou ignoré sans re-query. Approximation : on compte 1 créé si absent avant
        except Exception as e:
            report.erreurs.append(f"Fournisseur {f.nom}: {e}")


async def import_marques(
    conn: aiosqlite.Connection,
    marques: list[NotionMarque],
    report: ImportReport,
) -> None:
    for m in marques:
        try:
            cur = await conn.execute("SELECT id FROM fournisseurs WHERE nom = ?", (m.fournisseur_nom,))
            row = await cur.fetchone()
            fournisseur_id = row["id"] if row else None

            cur = await conn.execute(
                "SELECT id FROM marques WHERE nom = ? AND (fournisseur_id = ? OR (fournisseur_id IS NULL AND ? IS NULL))",
                (m.nom, fournisseur_id, fournisseur_id),
            )
            if await cur.fetchone() is not None:
                continue  # déjà présent

            await conn.execute(
                """INSERT INTO marques (nom, fournisseur_id, poids_kg_sac)
                   VALUES (?, ?, ?)""",
                (m.nom, fournisseur_id, m.poids_kg_sac),
            )
            report.marques_created += 1
        except Exception as e:
            report.erreurs.append(f"Marque {m.nom}: {e}")


async def import_lots(
    conn: aiosqlite.Connection,
    lots: list[NotionLot],
    report: ImportReport,
) -> None:
    for lot in lots:
        try:
            # Trouver la marque
            cur = await conn.execute("SELECT id FROM fournisseurs WHERE nom = ?", (lot.fournisseur_nom,))
            fournisseur_row = await cur.fetchone()
            fournisseur_id = fournisseur_row["id"] if fournisseur_row else None

            cur = await conn.execute(
                """SELECT id FROM marques
                   WHERE nom = ?
                   AND (fournisseur_id = ? OR (fournisseur_id IS NULL AND ? IS NULL))""",
                (lot.marque_nom, fournisseur_id, fournisseur_id),
            )
            marque_row = await cur.fetchone()
            if marque_row is None:
                # Marque absente : on la crée
                cur = await conn.execute(
                    """INSERT INTO marques (nom, fournisseur_id, poids_kg_sac)
                       VALUES (?, ?, ?)""",
                    (lot.marque_nom, fournisseur_id, lot.poids_sac_kg),
                )
                marque_id = cur.lastrowid
            else:
                marque_id = marque_row["id"]

            # Vérifier si le lot existe déjà (date + marque + sacs)
            cur = await conn.execute(
                """SELECT id FROM lots
                   WHERE marque_id = ? AND date_achat = ? AND sacs = ? AND poids_sac_kg = ?""",
                (marque_id, lot.date_achat, lot.sacs, lot.poids_sac_kg),
            )
            if await cur.fetchone() is not None:
                report.lots_skipped_duplicate += 1
                continue

            cur = await conn.execute(
                """INSERT INTO lots
                   (marque_id, date_achat, sacs, poids_sac_kg, prix_total_eur, fournisseur_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    marque_id,
                    lot.date_achat,
                    lot.sacs,
                    lot.poids_sac_kg,
                    lot.prix_total_eur,
                    fournisseur_id,
                ),
            )
            await conn.commit()
            lot_id = cur.lastrowid

            # Créer le mouvement d'ajout
            total_kg = lot.sacs * lot.poids_sac_kg
            await conn.execute(
                """INSERT INTO mouvements (type, date, sacs, poids_kg, lot_id, source, notes)
                   VALUES ('ajout', ?, ?, ?, ?, 'import_notion', ?)""",
                (
                    f"{lot.date_achat}T12:00:00",
                    lot.sacs,
                    total_kg,
                    lot_id,
                    f"Importé depuis Notion (lot {lot.sacs} sacs)",
                ),
            )
            await conn.commit()
            report.lots_created += 1
        except Exception as e:
            report.erreurs.append(f"Lot {lot.date_achat} {lot.marque_nom}: {e}")


async def import_mouvements(
    conn: aiosqlite.Connection,
    mouvements: list[NotionMouvement],
    report: ImportReport,
) -> None:
    for m in mouvements:
        try:
            # Éviter les doublons
            cur = await conn.execute(
                """SELECT id FROM mouvements
                   WHERE type = ? AND date = ? AND sacs = ? AND poids_kg = ?
                   AND source = 'import_notion'""",
                (m.type, m.date, m.sacs, m.poids_kg),
            )
            if await cur.fetchone() is not None:
                continue

            # Résoudre marque_id si possible (TODO si besoin)
            await conn.execute(
                """INSERT INTO mouvements (type, date, sacs, poids_kg, source, notes)
                   VALUES (?, ?, ?, ?, 'import_notion', ?)""",
                (m.type, m.date, m.sacs, m.poids_kg, m.notes),
            )
            report.mouvements_created += 1
        except Exception as e:
            report.erreurs.append(f"Mouvement {m.date} {m.sacs}: {e}")


# ----- Orchestration -----


async def import_from_notion(
    token: str,
    db_pellets_id: str,
    db_calendrier_id: str,
    db_path=None,
) -> ImportReport:
    """Importe les données depuis les 2 DBs Notion vers SQLite."""
    report = ImportReport()

    # 1. Lire les pages
    logger.info("Lecture DB Pellets...")
    pages_pellets = await _notion_query_database(db_pellets_id, token)
    marques = parse_pellets_pages(pages_pellets)

    logger.info("Lecture DB Calendrier...")
    pages_calendrier = await _notion_query_database(db_calendrier_id, token)

    # Construire l'index {page_id: nom_marque} depuis les pages Pellets
    marque_index: dict[str, str] = {}
    for page, marque in zip(pages_pellets, marques, strict=False):
        marque_index[page["id"]] = marque.nom

    mouvements = parse_calendrier_pages(pages_calendrier, marque_index)

    # 2. Extraire les fournisseurs uniques
    fournisseurs_uniq = {m.fournisseur_nom for m in marques if m.fournisseur_nom and m.fournisseur_nom != "?"}
    fournisseurs = [NotionFournisseur(nom=n) for n in sorted(fournisseurs_uniq)]

    # 3. Injecter dans SQLite
    async with connection(db_path) as conn:
        await import_fournisseurs(conn, fournisseurs, report)
        await conn.commit()
        await import_marques(conn, marques, report)
        await conn.commit()
        # (Lots et mouvements des DBs Notion = on dérive depuis les pages "Achat"
        # du calendrier si on n'a pas de DB Lots dédiée. On le fait plus tard.)
        await import_mouvements(conn, mouvements, report)
        await conn.commit()

    return report
