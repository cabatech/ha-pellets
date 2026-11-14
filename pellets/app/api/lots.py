"""API Lots (achats)."""

from __future__ import annotations

from datetime import date as date_t
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.db import connection
from app.schemas import Lot, LotCreate

router = APIRouter(prefix="/api/lots", tags=["lots"])


class LotWithDetails(Lot):
    """Lot enrichi du nom de marque + fournisseur."""

    marque_nom: str | None = None
    fournisseur_nom: str | None = None
    nb_mouvements: int = 0
    sacs_restants: int = 0  # pour info


def _row_to_lot_with_details(row) -> dict:
    """Convertit une Row en dict, sans les colonnes calculées."""
    return dict(row)


@router.get("", response_model=list[LotWithDetails])
async def list_lots(
    marque_id: int | None = Query(default=None),
    fournisseur_id: int | None = Query(default=None),
    date_from: date_t | None = Query(default=None),
    date_to: date_t | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[dict]:
    """Liste les lots, triés par date d'achat décroissante."""
    query = """
        SELECT l.*, m.nom AS marque_nom, f.nom AS fournisseur_nom,
               (SELECT COUNT(*) FROM mouvements WHERE lot_id = l.id) AS nb_mouvements
        FROM lots l
        LEFT JOIN marques m ON l.marque_id = m.id
        LEFT JOIN fournisseurs f ON l.fournisseur_id = f.id
    """
    conditions: list[str] = []
    params: list = []
    if marque_id is not None:
        conditions.append("l.marque_id = ?")
        params.append(marque_id)
    if fournisseur_id is not None:
        conditions.append("l.fournisseur_id = ?")
        params.append(fournisseur_id)
    if date_from is not None:
        conditions.append("l.date_achat >= ?")
        params.append(date_from.isoformat())
    if date_to is not None:
        conditions.append("l.date_achat <= ?")
        params.append(date_to.isoformat())
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY l.date_achat DESC LIMIT ?"
    params.append(limit)

    async with connection() as conn:
        cur = await conn.execute(query, params)
        return [_row_to_lot_with_details(r) for r in await cur.fetchall()]


@router.get("/{lot_id}", response_model=LotWithDetails)
async def get_lot(lot_id: int) -> dict:
    async with connection() as conn:
        cur = await conn.execute(
            """
            SELECT l.*, m.nom AS marque_nom, f.nom AS fournisseur_nom,
                   (SELECT COUNT(*) FROM mouvements WHERE lot_id = l.id) AS nb_mouvements
            FROM lots l
            LEFT JOIN marques m ON l.marque_id = m.id
            LEFT JOIN fournisseurs f ON l.fournisseur_id = f.id
            WHERE l.id = ?
            """,
            (lot_id,),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Lot introuvable")
    return _row_to_lot_with_details(row)


@router.post("", response_model=Lot, status_code=status.HTTP_201_CREATED)
async def create_lot(payload: LotCreate) -> dict:
    """Crée un lot d'achat. Peut créer la marque et le fournisseur à la volée."""

    async with connection() as conn:
        marque_id = payload.marque_id
        fournisseur_id = payload.fournisseur_id

        # 1. Créer le fournisseur si nouveau
        if payload.nouveau_fournisseur is not None:
            try:
                cur = await conn.execute(
                    "INSERT INTO fournisseurs (nom, notes) VALUES (?, ?)",
                    (payload.nouveau_fournisseur.nom, payload.nouveau_fournisseur.notes),
                )
                fournisseur_id = cur.lastrowid
            except Exception as e:
                if "UNIQUE constraint failed" in str(e):
                    cur = await conn.execute(
                        "SELECT id FROM fournisseurs WHERE nom = ?", (payload.nouveau_fournisseur.nom,)
                    )
                    row = await cur.fetchone()
                    fournisseur_id = row["id"]
                else:
                    raise

        # 2. Créer la marque si nouvelle
        if payload.nouvelle_marque is not None:
            try:
                cur = await conn.execute(
                    """INSERT INTO marques (nom, fournisseur_id, poids_kg_sac, notes)
                       VALUES (?, ?, ?, ?)""",
                    (
                        payload.nouvelle_marque.nom,
                        payload.nouvelle_marque.fournisseur_id or fournisseur_id,
                        payload.nouvelle_marque.poids_kg_sac,
                        payload.nouvelle_marque.notes,
                    ),
                )
                marque_id = cur.lastrowid
            except Exception as e:
                if "UNIQUE constraint failed" in str(e):
                    cur = await conn.execute(
                        "SELECT id FROM marques WHERE nom = ? AND (fournisseur_id = ? OR (fournisseur_id IS NULL AND ? IS NULL))",
                        (payload.nouvelle_marque.nom, fournisseur_id, fournisseur_id),
                    )
                    row = await cur.fetchone()
                    if row is None:
                        raise HTTPException(
                            status_code=409,
                            detail=f"Marque '{payload.nouvelle_marque.nom}' existe déjà pour un autre fournisseur",
                        ) from e
                    marque_id = row["id"]
                else:
                    raise

        # 3. Vérifier que la marque existe
        if marque_id is None:
            raise HTTPException(status_code=400, detail="marque_id ou nouvelle_marque requis")

        cur = await conn.execute("SELECT id FROM marques WHERE id = ?", (marque_id,))
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Marque {marque_id} introuvable")

        # 4. Insérer le lot
        try:
            cur = await conn.execute(
                """INSERT INTO lots
                   (marque_id, date_achat, sacs, poids_sac_kg, prix_total_eur, fournisseur_id, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    marque_id,
                    payload.date_achat.isoformat(),
                    payload.sacs,
                    payload.poids_sac_kg,
                    payload.prix_total_eur,
                    fournisseur_id,
                    payload.notes,
                ),
            )
            await conn.commit()
            lot_id = cur.lastrowid
        except Exception as e:
            if "FOREIGN KEY constraint failed" in str(e):
                raise HTTPException(status_code=400, detail="marque_id ou fournisseur_id invalide") from e
            if "CHECK constraint failed" in str(e):
                raise HTTPException(
                    status_code=400, detail="Valeurs invalides (sacs > 0, poids > 0, prix >= 0)"
                ) from e
            raise

        # 5. Insérer automatiquement le mouvement d'ajout (positif)
        total_kg = payload.sacs * payload.poids_sac_kg
        await conn.execute(
            """INSERT INTO mouvements (type, date, sacs, poids_kg, lot_id, source, notes)
               VALUES ('ajout', ?, ?, ?, ?, 'web_ui', ?)""",
            (
                f"{payload.date_achat.isoformat()}T12:00:00",
                payload.sacs,
                total_kg,
                lot_id,
                f"Achat lot #{lot_id} - {payload.sacs} sacs",
            ),
        )
        await conn.commit()

        cur = await conn.execute("SELECT * FROM lots WHERE id = ?", (lot_id,))
        return dict(await cur.fetchone())
