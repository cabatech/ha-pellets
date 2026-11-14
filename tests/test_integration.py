"""Intégration Pellets contre un vrai cœur HA, API simulée (pytest-homeassistant-custom-component)."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

URL = "http://pellets.test:8234"


def mock_api(aioclient_mock, kg=370.0, jours=111.0):
    aioclient_mock.get(f"{URL}/health", json={"status": "ok"})
    aioclient_mock.get(f"{URL}/api/stock", json={"poids_kg_total": kg, "sacs_total": 39})
    aioclient_mock.get(
        f"{URL}/api/stats/autonomie",
        json={"jours": jours, "conso_moyenne_kg_jour": 3.33, "stock_kg": kg, "methode": "x"},
    )
    aioclient_mock.get(f"{URL}/api/stats/prix-moyen", json={"prix_moyen_kg": 0.434})
    aioclient_mock.get(f"{URL}/api/stats/conso/summary", json={"kg_total": 15.0})
    aioclient_mock.get(f"{URL}/api/lots", json=[{"id": 4, "poids_sac_kg": 10.0}])
    aioclient_mock.post(f"{URL}/api/mouvements", json={"id": 1}, status=201)


async def test_config_flow(hass, aioclient_mock):
    mock_api(aioclient_mock)
    result = await hass.config_entries.flow.async_init(
        "pellets", context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"url": URL + "/"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["url"] == URL


async def test_entities_and_button(hass, aioclient_mock):
    hass.config.language = "fr"  # entity_id issus des noms traduits, comme en prod
    mock_api(aioclient_mock, kg=25.0, jours=None)
    entry = MockConfigEntry(domain="pellets", data={"url": URL})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    states = {s.entity_id: s.state for s in hass.states.async_all()}
    assert states["sensor.pellets_stock"] == "25.0"
    assert states["sensor.pellets_autonomie"] == "unknown"
    assert states["binary_sensor.pellets_stock_bas"] == "on"  # 25 kg < 30 kg

    await hass.services.async_call(
        "button", "press", {"entity_id": "button.pellets_destocker_un_sac"}, blocking=True
    )
    posts = [c for c in aioclient_mock.mock_calls if c[0] == "POST"]
    assert posts[0][2]["sacs"] == -1
    assert posts[0][2]["poids_kg"] == -10.0 and posts[0][2]["lot_id"] == 4  # dernier lot


async def test_all_sensors_keep_statistics(hass, aioclient_mock):
    """Chaque capteur numérique a une state_class (sinon HA signale la perte des statistiques v1)."""
    hass.config.language = "fr"
    mock_api(aioclient_mock)
    entry = MockConfigEntry(domain="pellets", data={"url": URL})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    sensors = [s for s in hass.states.async_all("sensor") if s.entity_id.startswith("sensor.pellets_")]
    assert len(sensors) == 6
    assert all(s.attributes.get("state_class") == "measurement" for s in sensors)
