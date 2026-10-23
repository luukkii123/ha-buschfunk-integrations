"""Buschfunk actions: independent from config-entry availability."""
from homeassistant.const import Platform
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.exceptions import ConfigEntryAuthFailed,ConfigEntryNotReady
from .api import BuschfunkApi,ApiAuthError,ApiError
from homeassistant.helpers import config_validation as cv
from .const import DEFAULT_TIMEOUT,DOMAIN
from .coordinator import BuschfunkDaten,DienstraumKoordinator
from .services import async_register_services

PLATFORMS=[Platform.SENSOR]
CONFIG_SCHEMA=cv.config_entry_only_config_schema(DOMAIN)

async def async_setup(hass:HomeAssistant,config:dict)->bool:
    async_register_services(hass)
    return True

async def async_setup_entry(hass:HomeAssistant,entry:ConfigEntry)->bool:
    api=BuschfunkApi(async_get_clientsession(hass),entry.data['url'],entry.data['api_key'],entry.options.get('timeout',DEFAULT_TIMEOUT))
    try:await api.chats(limit=1)
    except ApiAuthError as err:raise ConfigEntryAuthFailed('invalid_auth') from err
    except ApiError as err:raise ConfigEntryNotReady('cannot_connect') from err
    koordinator=DienstraumKoordinator(hass,entry,api)
    # Not first_refresh: a Buschfunk without service rooms must not block setup.
    await koordinator.async_refresh()
    entry.runtime_data=BuschfunkDaten(api,koordinator)
    await hass.config_entries.async_forward_entry_setups(entry,PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True

async def async_update_options(hass:HomeAssistant,entry:ConfigEntry)->None:
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass:HomeAssistant,entry:ConfigEntry)->bool:
    ok=await hass.config_entries.async_unload_platforms(entry,PLATFORMS)
    if ok:entry.runtime_data=None
    return ok
