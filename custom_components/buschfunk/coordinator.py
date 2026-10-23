"""Active service rooms (GET), polled rarely and refreshed after changes."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import timedelta
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator,UpdateFailed
from .api import ApiAuthError,ApiError,ApiForbiddenError,ApiRateLimitError,BuschfunkApi
from .const import DOMAIN

_LOGGER=logging.getLogger(__name__)
INTERVALL=timedelta(minutes=5)

class DienstraumKoordinator(DataUpdateCoordinator[dict]):
    def __init__(self,hass:HomeAssistant,entry:ConfigEntry,api:BuschfunkApi):
        super().__init__(hass,_LOGGER,config_entry=entry,name=DOMAIN,update_interval=INTERVALL)
        self.api=api

    async def _async_update_data(self)->dict:
        try:return await self.api.dienstraeume()
        # 403 (MCP key, or a core without service rooms) only blocks this sensor.
        except ApiForbiddenError as err:raise UpdateFailed(translation_domain=DOMAIN,translation_key='forbidden') from err
        except ApiAuthError as err:raise ConfigEntryAuthFailed(translation_domain=DOMAIN,translation_key='invalid_auth') from err
        except ApiRateLimitError as err:raise UpdateFailed(translation_domain=DOMAIN,translation_key='rate_limited_later',retry_after=err.retry_after) from err
        except ApiError as err:raise UpdateFailed(translation_domain=DOMAIN,translation_key='rooms_unavailable') from err

@dataclass
class BuschfunkDaten:
    api:BuschfunkApi
    koordinator:DienstraumKoordinator
