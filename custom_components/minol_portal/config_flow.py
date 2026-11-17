"""UI configuration, isolated credential validation and reauthentication."""

import hashlib

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import CONF_REFRESH_HOURS, CONF_TENANT, DEFAULT_REFRESH_HOURS, DOMAIN
from .model import discover_meters, entry_title, query_period
from .portal import Credentials, PortalClient
from .portal.errors import AuthenticationError, PortalError, SelectionError


def login_schema(defaults=None):
    defaults = defaults or {}
    return vol.Schema({
        vol.Required(CONF_EMAIL, default=defaults.get(CONF_EMAIL, "")): str,
        vol.Required(CONF_PASSWORD): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
        vol.Optional(CONF_TENANT, default=defaults.get(CONF_TENANT, "")): str,
    })


async def async_validate_login(hass, user_input):
    credentials = Credentials(user_input[CONF_EMAIL].strip(), user_input[CONF_PASSWORD])
    session = async_create_clientsession(hass, auto_cleanup=False, cookie_jar=aiohttp.CookieJar(quote_cookie=False))
    try:
        snapshot = await PortalClient(session, credentials).fetch_snapshot(
            query_period(), user_input.get(CONF_TENANT) or None)
        discover_meters(snapshot)
        return credentials, snapshot
    finally:
        # The connector belongs to HA. close() is forbidden even with auto_cleanup=False.
        session.detach()


class MinolConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                credentials, snapshot = await async_validate_login(self.hass, user_input)
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except SelectionError:
                errors["base"] = "invalid_selection"
            except (PortalError, ValueError):
                errors["base"] = "cannot_connect"
            else:
                unique_id = hashlib.sha256(snapshot.selected_tenant["userNumber"].encode()).hexdigest()
                data = {**user_input, CONF_EMAIL: credentials.email,
                        CONF_TENANT: snapshot.selected_tenant["userNumber"]}
                if self.source == config_entries.SOURCE_REAUTH:
                    entry = self._get_reauth_entry()
                    if unique_id != entry.unique_id:
                        return self.async_abort(reason="wrong_account")
                    return self.async_update_reload_and_abort(entry, data=data)
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=entry_title(snapshot.selected_tenant), data=data)
        return self.async_show_form(step_id="user", data_schema=login_schema(user_input), errors=errors)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return MinolOptionsFlow()


class MinolOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        options = self.config_entry.options
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required(CONF_REFRESH_HOURS, default=options.get(CONF_REFRESH_HOURS, DEFAULT_REFRESH_HOURS)):
                vol.All(vol.Coerce(int), vol.Range(min=1, max=168)),
        }))
