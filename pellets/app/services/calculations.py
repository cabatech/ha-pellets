"""Fonctions de calcul métier (autonomie, stats conso, etc.)."""

from __future__ import annotations

from datetime import date, timedelta

import aiosqlite

from app.schemas import AutonomieJours, ConsoJour


async def get_stock(conn: aiosqlite.Connection) -> tuple[float, int]:
    """Retourne (poids_kg_total, sacs_total) depuis v_stock."""
    cur = await conn.execute("SELECT poids_kg_total, sacs_total FROM v_stock")
    row = await cur.fetchone()
    return (row["poids_kg_total"], row["sacs_total"])


async def get_conso_journaliere(
    conn: aiosqlite.Connection,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[ConsoJour]:
    """Conso par jour (vue), filtrable."""
    query = "SELECT jour, kg_consommes, sacs_consommes FROM v_conso_journaliere"
    params: list[str] = []
    conditions: list[str] = []
    if date_from is not None:
        conditions.append("jour >= ?")
        params.append(date_from.isoformat())
    if date_to is not None:
        conditions.append("jour <= ?")
        params.append(date_to.isoformat())
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY jour"

    cur = await conn.execute(query, params)
    rows = await cur.fetchall()
    return [
        ConsoJour(
            jour=row["jour"],
            kg_consommes=row["kg_consommes"],
            sacs_consommes=row["sacs_consommes"],
        )
        for row in rows
    ]


async def get_prix_moyen_kg(conn: aiosqlite.Connection) -> float | None:
    """Prix moyen d'achat au kg."""
    cur = await conn.execute("SELECT prix_moyen_kg FROM v_prix_moyen_achat")
    row = await cur.fetchone()
    return row["prix_moyen_kg"]


async def get_cout_total(conn: aiosqlite.Connection) -> float:
    """Coût total des achats."""
    cur = await conn.execute("SELECT cout_total_eur FROM v_cout_total")
    row = await cur.fetchone()
    return row["cout_total_eur"]


async def get_autonomie_jours(conn: aiosqlite.Connection) -> AutonomieJours:
    """Estime l'autonomie restante en jours.

    Méthode : conso moyenne par jour calendaire sur les 30 derniers jours
    (limitée à l'historique réel), divisée par le stock actuel. Fallback 7j.

    On borne le nombre de jours à l'historique réel (1er jour de conso → today),
    pas 30 aveuglément, pour que les premiers jours d'utilisation ne soient pas
    sous-estimés.
    """
    stock_kg, _ = await get_stock(conn)
    today = date.today()

    # Conso moyenne 30j — limitée à l'historique réel
    conso_30j = await get_conso_journaliere(conn, date_from=today - timedelta(days=30))
    total_kg_30j = sum(c.kg_consommes for c in conso_30j)
    if conso_30j:
        first_day = min(c.jour for c in conso_30j)
        nb_jours_30j = min((today - first_day).days + 1, 30)
    else:
        nb_jours_30j = 0

    if total_kg_30j > 0 and nb_jours_30j > 0:
        conso_moyenne = total_kg_30j / nb_jours_30j
        if conso_moyenne > 0:
            return AutonomieJours(
                jours=round(stock_kg / conso_moyenne, 1),
                conso_moyenne_kg_jour=round(conso_moyenne, 2),
                stock_kg=stock_kg,
                methode="conso_moyenne_30j",
            )

    # Fallback : conso moyenne 7j
    conso_7j = await get_conso_journaliere(conn, date_from=today - timedelta(days=7))
    total_kg_7j = sum(c.kg_consommes for c in conso_7j)
    if conso_7j:
        first_day = min(c.jour for c in conso_7j)
        nb_jours_7j = min((today - first_day).days + 1, 7)
    else:
        nb_jours_7j = 0
    if total_kg_7j > 0 and nb_jours_7j > 0:
        conso_moyenne = total_kg_7j / nb_jours_7j
        if conso_moyenne > 0:
            return AutonomieJours(
                jours=round(stock_kg / conso_moyenne, 1),
                conso_moyenne_kg_jour=round(conso_moyenne, 2),
                stock_kg=stock_kg,
                methode="conso_moyenne_7j",
            )

    return AutonomieJours(
        jours=None,
        conso_moyenne_kg_jour=None,
        stock_kg=stock_kg,
        methode="insuffisant",
    )


async def get_conso_periode(
    conn: aiosqlite.Connection,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[float, int, int]:
    """Conso totale sur une période (kg, sacs, jours)."""
    rows = await get_conso_journaliere(conn, date_from, date_to)
    kg = sum(r.kg_consommes for r in rows)
    sacs = sum(r.sacs_consommes for r in rows)
    jours = len(rows)
    return (kg, sacs, jours)
