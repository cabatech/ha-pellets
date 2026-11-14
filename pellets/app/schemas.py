"""Schémas Pydantic (entrée/sortie API)."""

from __future__ import annotations

from datetime import date as date_t
from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ----- Enums -----


class MouvementType(StrEnum):
    """Type de mouvement de stock."""

    DESTOCKAGE = "destockage"
    AJOUT = "ajout"
    INVENTAIRE = "inventaire"
    CORRECTION = "correction"


class MouvementSource(StrEnum):
    """Origine de l'écriture (traçabilité)."""

    HA_BUTTON = "ha_button"
    WEB_UI = "web_ui"
    AGENT = "agent"
    IMPORT_NOTION = "import_notion"
    SCRIPT = "script"

# ----- Fournisseur -----


class FournisseurBase(BaseModel):
    nom: Annotated[str, Field(min_length=1, max_length=100)]
    notes: str | None = None


class FournisseurCreate(FournisseurBase):
    pass


class Fournisseur(FournisseurBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


# ----- Marque -----


class MarqueBase(BaseModel):
    nom: Annotated[str, Field(min_length=1, max_length=100)]
    fournisseur_id: int | None = None
    poids_kg_sac: float | None = Field(default=None, gt=0)
    notes: str | None = None


class MarqueCreate(MarqueBase):
    pass


class Marque(MarqueBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


# ----- Lot -----


class LotBase(BaseModel):
    marque_id: int
    date_achat: date_t
    sacs: Annotated[int, Field(gt=0)]
    poids_sac_kg: Annotated[float, Field(gt=0)]
    prix_total_eur: Annotated[float, Field(ge=0)]
    fournisseur_id: int | None = None
    notes: str | None = None

    @field_validator("date_achat", mode="before")
    @classmethod
    def _parse_date(cls, v: object) -> object:
        """Accepte aussi des datetime ISO."""
        if isinstance(v, str) and "T" in v:
            return datetime.fromisoformat(v).date()
        return v


class LotCreate(LotBase):
    """Création d'un lot (depuis Web UI achat)."""

    marque_id: int | None = None  # Optionnel si on fournit nouvelle_marque
    # Si la marque n'existe pas, on peut la créer à la volée
    nouvelle_marque: MarqueCreate | None = None
    nouveau_fournisseur: FournisseurCreate | None = None


class Lot(LotBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


# ----- Mouvement -----


class MouvementBase(BaseModel):
    type: MouvementType
    date: datetime
    sacs: int  # peut être négatif (destockage)
    poids_kg: float  # peut être négatif (destockage)
    lot_id: int | None = None
    notes: str | None = None

    @field_validator("date", mode="before")
    @classmethod
    def _parse_date(cls, v: object) -> object:
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v


class MouvementCreate(MouvementBase):
    """Création d'un mouvement (depuis HA bouton, Web UI, etc.)."""

    source: MouvementSource = MouvementSource.WEB_UI


class Mouvement(MouvementBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: MouvementSource
    created_at: datetime


# ----- Vues / réponses agrégées -----


class Stock(BaseModel):
    """Stock actuel."""

    poids_kg_total: float
    sacs_total: int


class ConsoJour(BaseModel):
    """Conso d'un jour (vue v_conso_journaliere)."""

    jour: date_t
    kg_consommes: float
    sacs_consommes: int


class PrixMoyenAchat(BaseModel):
    """Prix moyen d'achat au kg."""

    prix_moyen_kg: float | None


class CoutTotal(BaseModel):
    """Coût total des achats."""

    cout_total_eur: float


class AutonomieJours(BaseModel):
    """Estimation du nombre de jours d'autonomie."""

    jours: float | None
    conso_moyenne_kg_jour: float | None
    stock_kg: float
    methode: str  # "conso_moyenne_30j" | "conso_moyenne_7j" | "insuffisant"


# ----- Form helpers (Web UI) -----


class AchatForm(BaseModel):
    """Données du formulaire d'achat (Web UI)."""

    date_achat: date_t
    fournisseur_nom: str
    marque_nom: str
    sacs: Annotated[int, Field(gt=0)]
    poids_sac_kg: Annotated[float, Field(gt=0)]
    prix_total_eur: Annotated[float, Field(ge=0)]
    notes: str | None = None
