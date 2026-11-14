"""API Mouvements (destockage / ajout / inventaire / correction)."""

from __future__ import annotations

from datetime import date as date_t
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import ConfigDict

from app.db import connection
from app.schemas import Mouvement, MouvementCreate, MouvementType

router = APIRouter(prefix="/api/mouvements", tags=["mouvements"])


class MouvementWithDetails(Mouvement):
    """Mouvement enrichi (nom de marque / fournisseur du lot lié)."""

    model_config = ConfigDict(from_attributes=True)

    marque_nom: str | None = None
    fournisseur_nom: str | None = None


@router.get("", response_model=list[MouvementWithDetails])
async def list_mouvements(
    type: MouvementType | None = Query(default=None),
    date_from: date_t | None = Query(default=None),
    date_to: date_t | None = Query(default=None),
    lot_id: int | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[dict]:
    """Liste les mouvements, triés par date décroissante."""
    query = """
        SELECT m.*,
               mk.nom AS marque_nom,
               f.nom AS fournisseur_nom
        FROM mouvements m
        LEFT JOIN lots l ON m.lot_id = l.id
        LEFT JOIN marques mk ON l.marque_id = mk.id
        LEFT JOIN fournisseurs f ON l.fournisseur_id = f.id
    """
    conditions: list[str] = []
    params: list = []
    if type is not None:
        conditions.append("m.type = ?")
        params.append(type.value)
    if date_from is not None:
        conditions.append("date(m.date) >= ?")
        params.append(date_from.isoformat())
    if date_to is not None:
        conditions.append("date(m.date) <= ?")
        params.append(date_to.isoformat())
    if lot_id is not None:
        conditions.append("m.lot_id = ?")
        params.append(lot_id)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY m.date DESC LIMIT ?"
    params.append(limit)

    async with connection() as conn:
        cur = await conn.execute(query, params)
        return [dict(r) for r in await cur.fetchall()]


@router.get("/{mouvement_id}", response_model=MouvementWithDetails)
async def get_mouvement(mouvement_id: int) -> dict:
    async with connection() as conn:
        cur = await conn.execute(
            """
            SELECT m.*,
                   mk.nom AS marque_nom,
                   f.nom AS fournisseur_nom
            FROM mouvements m
            LEFT JOIN lots l ON m.lot_id = l.id
            LEFT JOIN marques mk ON l.marque_id = mk.id
            LEFT JOIN fournisseurs f ON l.fournisseur_id = f.id
            WHERE m.id = ?
            """,
            (mouvement_id,),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Mouvement introuvable")
    return dict(row)


@router.post("", response_model=Mouvement, status_code=status.HTTP_201_CREATED)
async def create_mouvement(payload: MouvementCreate) -> dict:
    """Crée un mouvement (depuis HA, Web UI, agent, etc.)."""
    async with connection() as conn:
        try:
            cur = await conn.execute(
                """INSERT INTO mouvements
                   (type, date, sacs, poids_kg, lot_id, source, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    payload.type.value,
                    payload.date.isoformat(),
                    payload.sacs,
                    payload.poids_kg,
                    payload.lot_id,
                    payload.source.value,
                    payload.notes,
                ),
            )
            await conn.commit()
            mid = cur.lastrowid
        except Exception as e:
            if "FOREIGN KEY constraint failed" in str(e):
                raise HTTPException(status_code=400, detail="lot_id invalide") from e
            if "CHECK constraint failed" in str(e):
                raise HTTPException(status_code=400, detail="Type de mouvement invalide") from e
            raise

        cur = await conn.execute("SELECT * FROM mouvements WHERE id = ?", (mid,))
        return dict(await cur.fetchone())


@router.delete("/{mouvement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mouvement(mouvement_id: int) -> None:
    """Supprime un mouvement (utile pour corriger une erreur)."""
    async with connection() as conn:
        cur = await conn.execute("DELETE FROM mouvements WHERE id = ?", (mouvement_id,))
        await conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Mouvement introuvable")
