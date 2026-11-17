"""Home Assistant integration for the Minol resident portal."""

import aiohttp

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .coordinator import MinolCoordinator
from .portal import Credentials, PortalClient


PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass, entry):
    # HA owns the shared connector and detaches this cookie session on unload.
    session = async_create_clientsession(hass, cookie_jar=aiohttp.CookieJar(quote_cookie=False))
    client = PortalClient(session, Credentials(entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD]))
    coordinator = MinolCoordinator(hass, entry, client, session)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
