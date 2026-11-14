"""Tests des schémas Pydantic."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from app.schemas import (
    AchatForm,
    FournisseurCreate,
    LotCreate,
    MouvementCreate,
    MouvementSource,
    MouvementType,
)


def test_fournisseur_create_minimal() -> None:
    f = FournisseurCreate(nom="Bois Rosa")
    assert f.nom == "Bois Rosa"
    assert f.notes is None


def test_fournisseur_create_empty_nom_rejected() -> None:
    with pytest.raises(ValidationError):
        FournisseurCreate(nom="")


def test_lot_create_valid() -> None:
    lot = LotCreate(
        marque_id=1,
        date_achat=date(2026, 1, 15),
        sacs=10,
        poids_sac_kg=15.0,
        prix_total_eur=85.50,
    )
    assert lot.sacs == 10
    assert lot.poids_sac_kg == 15.0


def test_lot_create_rejects_zero_sacs() -> None:
    with pytest.raises(ValidationError):
        LotCreate(
            marque_id=1,
            date_achat=date(2026, 1, 15),
            sacs=0,
            poids_sac_kg=15.0,
            prix_total_eur=85.50,
        )


def test_lot_create_accepts_iso_datetime_as_date() -> None:
    """Si l'utilisateur envoie une ISO datetime, on extrait la date."""
    lot = LotCreate(
        marque_id=1,
        date_achat="2026-01-15T10:30:00",
        sacs=10,
        poids_sac_kg=15.0,
        prix_total_eur=85.50,
    )
    assert lot.date_achat == date(2026, 1, 15)


def test_mouvement_destockage_negatif() -> None:
    m = MouvementCreate(
        type=MouvementType.DESTOCKAGE,
        date=datetime(2026, 1, 15, 18, 30),
        sacs=-1,
        poids_kg=-10.0,
    )
    assert m.sacs == -1
    assert m.source == MouvementSource.WEB_UI  # default


def test_mouvement_accepts_iso_with_z() -> None:
    m = MouvementCreate(
        type=MouvementType.AJOUT,
        date="2026-01-15T10:00:00Z",
        sacs=1,
        poids_kg=10.0,
    )
    assert m.date.tzinfo is not None


def test_achat_form_valid() -> None:
    f = AchatForm(
        date_achat=date(2026, 1, 15),
        fournisseur_nom="Bois Rosa",
        marque_nom="Piveteau",
        sacs=10,
        poids_sac_kg=15.0,
        prix_total_eur=85.50,
    )
    assert f.fournisseur_nom == "Bois Rosa"
