"""One isolated portal session and one update cycle per config entry."""

from dataclasses import dataclass
from datetime import timedelta
import logging

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_REFRESH_HOURS, CONF_TENANT, DEFAULT_REFRESH_HOURS
from .history import MinolHistory
from .model import Meter, query_period
from .portal import PortalClient, PortalSnapshot
from .portal.errors import AuthenticationError, PortalError


_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MinolData:
    snapshot: PortalSnapshot
    meters: dict[str, Meter]


class MinolCoordinator(DataUpdateCoordinator[MinolData]):
    def __init__(self, hass, entry, client: PortalClient, session):
        super().__init__(hass, _LOGGER, config_entry=entry, name="Minol Verbrauchsanzeige",
                         update_interval=timedelta(hours=entry.options.get(CONF_REFRESH_HOURS, DEFAULT_REFRESH_HOURS)))
        self.client = client
        self.session = session
        self.entry = entry
        self.history = MinolHistory(hass, entry.entry_id)

    async def _async_update_data(self):
        try:
            period = query_period(dt_util.now().date())
            snapshot = await self.client.fetch_snapshot(
                period, self.entry.data.get(CONF_TENANT) or None, monthly=True)
            meters = await self.history.async_update(snapshot)
            return MinolData(snapshot, meters)
        except AuthenticationError as error:
            raise ConfigEntryAuthFailed("Die Minol-Anmeldung muss erneuert werden.") from error
        except (PortalError, ValueError, OSError) as error:
            raise UpdateFailed("Minol-Daten konnten nicht eindeutig geladen werden.") from error
