"""Entité de base : un seul appareil « Pellets » par entrée."""

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PelletsCoordinator
from .const import DOMAIN


class PelletsEntity(CoordinatorEntity[PelletsCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: PelletsCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Pellets",
            entry_type=DeviceEntryType.SERVICE,
        )
