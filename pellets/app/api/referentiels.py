"""API CRUD fournisseurs + marques (référentiels)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.db import connection
from app.schemas import Fournisseur, FournisseurCreate, Marque, MarqueCreate

router = APIRouter(prefix="/api", tags=["référentiels"])


# ----- Fournisseurs -----


@router.get("/fournisseurs", response_model=list[Fournisseur])
async def list_fournisseurs() -> list[dict]:
    async with connection() as conn:
        cur = await conn.execute("SELECT * FROM fournisseurs ORDER BY nom")
        return [dict(r) for r in await cur.fetchall()]


@router.post("/fournisseurs", response_model=Fournisseur, status_code=status.HTTP_201_CREATED)
async def create_fournisseur(payload: FournisseurCreate) -> dict:
    async with connection() as conn:
        try:
            cur = await conn.execute(
                "INSERT INTO fournisseurs (nom, notes) VALUES (?, ?)",
                (payload.nom, payload.notes),
            )
            await conn.commit()
            fid = cur.lastrowid
            cur = await conn.execute("SELECT * FROM fournisseurs WHERE id = ?", (fid,))
            return dict(await cur.fetchone())
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                raise HTTPException(status_code=409, detail=f"Fournisseur '{payload.nom}' existe déjà") from e
            raise


@router.get("/fournisseurs/{fournisseur_id}", response_model=Fournisseur)
async def get_fournisseur(fournisseur_id: int) -> dict:
    async with connection() as conn:
        cur = await conn.execute("SELECT * FROM fournisseurs WHERE id = ?", (fournisseur_id,))
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Fournisseur introuvable")
    return dict(row)


# ----- Marques -----


class MarqueWithFournisseur(Marque):
    """Marque enrichie du nom du fournisseur."""

    fournisseur_nom: str | None = None


@router.get("/marques", response_model=list[MarqueWithFournisseur])
async def list_marques() -> list[dict]:
    async with connection() as conn:
        cur = await conn.execute(
            """
            SELECT m.*, f.nom AS fournisseur_nom
            FROM marques m
            LEFT JOIN fournisseurs f ON m.fournisseur_id = f.id
            ORDER BY m.nom
            """
        )
        return [dict(r) for r in await cur.fetchall()]


@router.post("/marques", response_model=Marque, status_code=status.HTTP_201_CREATED)
async def create_marque(payload: MarqueCreate) -> dict:
    async with connection() as conn:
        try:
            cur = await conn.execute(
                """INSERT INTO marques (nom, fournisseur_id, poids_kg_sac, notes)
                   VALUES (?, ?, ?, ?)""",
                (payload.nom, payload.fournisseur_id, payload.poids_kg_sac, payload.notes),
            )
            await conn.commit()
            mid = cur.lastrowid
            cur = await conn.execute("SELECT * FROM marques WHERE id = ?", (mid,))
            return dict(await cur.fetchone())
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                raise HTTPException(
                    status_code=409, detail=f"Marque '{payload.nom}' existe déjà pour ce fournisseur"
                ) from e
            raise


@router.get("/marques/{marque_id}", response_model=MarqueWithFournisseur)
async def get_marque(marque_id: int) -> dict:
    async with connection() as conn:
        cur = await conn.execute(
            """
            SELECT m.*, f.nom AS fournisseur_nom
            FROM marques m
            LEFT JOIN fournisseurs f ON m.fournisseur_id = f.id
            WHERE m.id = ?
            """,
            (marque_id,),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Marque introuvable")
    return dict(row)
