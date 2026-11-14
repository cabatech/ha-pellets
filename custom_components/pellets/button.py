"""Bouton « Déstocker un sac » (dernier lot acheté)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PelletsConfigEntry
from .entity import PelletsEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: PelletsConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([PelletsDestocker(entry.runtime_data, "destocker")])


class PelletsDestocker(PelletsEntity, ButtonEntity):
    _attr_icon = "mdi:sack"

    async def async_press(self) -> None:
        await self.coordinator.async_destocker()
