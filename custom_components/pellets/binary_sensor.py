"""Alerte stock bas."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PelletsConfigEntry
from .const import SEUIL_AUTONOMIE_J, SEUIL_STOCK_KG
from .entity import PelletsEntity


def stock_bas(data: dict) -> bool:
    """Vrai si stock < 30 kg ou autonomie connue < 7 jours."""
    jours = data["autonomie"]["jours"]
    return data["stock"]["poids_kg_total"] < SEUIL_STOCK_KG or (
        jours is not None and jours < SEUIL_AUTONOMIE_J
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: PelletsConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([PelletsStockBas(entry.runtime_data, "stock_bas")])


class PelletsStockBas(PelletsEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def is_on(self) -> bool:
        return stock_bas(self.coordinator.data)
