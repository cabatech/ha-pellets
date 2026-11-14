"""Capteurs : stock, autonomie, conso, prix."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfMass, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PelletsConfigEntry
from .entity import PelletsEntity


@dataclass(frozen=True, kw_only=True)
class PelletsSensorDescription(SensorEntityDescription):
    value: Callable[[dict], float | None]


SENSORS = (
    PelletsSensorDescription(
        key="stock_kg",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: d["stock"]["poids_kg_total"],
    ),
    PelletsSensorDescription(
        key="stock_sacs",
        native_unit_of_measurement="sacs",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: d["stock"]["sacs_total"],
    ),
    PelletsSensorDescription(
        key="autonomie",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value=lambda d: d["autonomie"]["jours"],
    ),
    PelletsSensorDescription(
        key="conso_moyenne",
        native_unit_of_measurement="kg/j",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value=lambda d: d["autonomie"]["conso_moyenne_kg_jour"],
    ),
    PelletsSensorDescription(
        key="prix_moyen",
        native_unit_of_measurement="€/kg",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value=lambda d: d["prix"]["prix_moyen_kg"],
    ),
    PelletsSensorDescription(
        key="conso_hier",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: d["hier"]["kg_total"],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: PelletsConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(PelletsSensor(entry.runtime_data, desc) for desc in SENSORS)


class PelletsSensor(PelletsEntity, SensorEntity):
    entity_description: PelletsSensorDescription

    def __init__(self, coordinator, description: PelletsSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value(self.coordinator.data)
