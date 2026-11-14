"""Intégration Home Assistant de l'app Pellets (API REST locale)."""

from __future__ import annotations

from datetime import timedelta
import logging

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]

type PelletsConfigEntry = ConfigEntry[PelletsCoordinator]


class PelletsCoordinator(DataUpdateCoordinator[dict]):
    """Interroge l'API toutes les 5 minutes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=timedelta(minutes=5)
        )
        self.url = entry.data[CONF_URL].rstrip("/")
        self.session = async_get_clientsession(hass)

    async def _get(self, path: str, params: dict | None = None) -> dict:
        async with self.session.get(
            f"{self.url}{path}", params=params, timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _async_update_data(self) -> dict:
        hier = (dt_util.now().date() - timedelta(days=1)).isoformat()
        try:
            return {
                "stock": await self._get("/api/stock"),
                "autonomie": await self._get("/api/stats/autonomie"),
                "prix": await self._get("/api/stats/prix-moyen"),
                "hier": await self._get(
                    "/api/stats/conso/summary", {"date_from": hier, "date_to": hier}
                ),
            }
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"API Pellets injoignable : {err}") from err

    async def async_destocker(self) -> None:
        """Déstocke un sac du dernier lot acheté (son poids de sac), puis rafraîchit."""
        try:
            lots = await self._get("/api/lots", {"limit": 1})
        except (aiohttp.ClientError, TimeoutError) as err:
            raise HomeAssistantError(f"API Pellets injoignable : {err}") from err
        if not lots:
            raise HomeAssistantError("Aucun lot enregistré : saisir un achat d'abord")
        lot = lots[0]
        payload = {
            "type": "destockage",
            "date": dt_util.now().isoformat(),
            "sacs": -1,
            "poids_kg": -lot["poids_sac_kg"],
            "lot_id": lot["id"],
            "source": "ha_button",
            "notes": "Home Assistant",
        }
        try:
            async with self.session.post(
                f"{self.url}/api/mouvements", json=payload, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                resp.raise_for_status()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise HomeAssistantError(f"Déstockage refusé par l'API Pellets : {err}") from err
        await self.async_request_refresh()


async def async_setup_entry(hass: HomeAssistant, entry: PelletsConfigEntry) -> bool:
    coordinator = PelletsCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PelletsConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
