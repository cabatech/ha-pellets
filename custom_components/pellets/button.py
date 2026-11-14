"""Bouton « Déstocker un sac »."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PelletsConfigEntry
from .const import CONF_POIDS_SAC, DEFAULT_POIDS_SAC
from .entity import PelletsEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: PelletsConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([PelletsDestocker(entry.runtime_data, "destocker")])


class PelletsDestocker(PelletsEntity, ButtonEntity):
    _attr_icon = "mdi:sack"

    async def async_press(self) -> None:
        data = self.coordinator.config_entry.data
        await self.coordinator.async_destocker(1, data.get(CONF_POIDS_SAC, DEFAULT_POIDS_SAC))
