"""Home Assistant integration for the Minol resident portal."""

import aiohttp

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import DOMAIN
from .coordinator import MinolCoordinator
from .portal import Credentials, PortalClient


PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass, entry):
    # HA owns the shared connector and detaches this cookie session on unload.
    session = async_create_clientsession(hass, cookie_jar=aiohttp.CookieJar(quote_cookie=False))
    client = PortalClient(session, Credentials(entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD]))
    coordinator = MinolCoordinator(hass, entry, client, session)
    cached = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if cached is None:
        await coordinator.async_config_entry_first_refresh()
    else:
        coordinator.data, coordinator.last_update_success = cached
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if cached is not None:
        # A UI reload must not wait for twelve months of network requests.
        entry.async_create_background_task(
            hass, coordinator.async_refresh(), "Minol refresh after reload")
    return True


async def _async_options_updated(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator = entry.runtime_data
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = (
            coordinator.data, coordinator.last_update_success)
    return unloaded


async def async_remove_entry(hass, entry):
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
