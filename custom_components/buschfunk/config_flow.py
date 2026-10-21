"""Native configuration, connection checks, key replacement and reauthentication."""
from homeassistant.config_entries import ConfigFlow,OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector,TextSelectorConfig,TextSelectorType,NumberSelector,NumberSelectorConfig,NumberSelectorMode
import voluptuous as vol
from .api import BuschfunkApi,ApiError,ApiAuthError,normalize_url
from .const import DOMAIN,DEFAULT_TIMEOUT

async def validate(hass,data):
    await BuschfunkApi(async_get_clientsession(hass),data['url'],data['api_key']).chats(limit=1)

def schema(data=None,key_only=False):
    data=data or {};fields={}
    if not key_only:fields[vol.Required('url',default=data.get('url',''))]=TextSelector(TextSelectorConfig(type=TextSelectorType.URL))
    # Keys are never repopulated in forms, screenshots or description placeholders.
    fields[vol.Required('api_key')]=TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
    return vol.Schema(fields)

class BuschfunkConfigFlow(ConfigFlow,domain=DOMAIN):
    VERSION=1
    async def _connection(self,user_input,step,entry=None):
        errors={}
        if user_input is not None:
            try:
                data={'url':normalize_url(entry.data['url'] if step=='reauth_confirm' else user_input['url']),'api_key':user_input['api_key'].strip()}
                if not data['api_key']:raise ApiAuthError('invalid_auth')
                await validate(self.hass,data)
                await self.async_set_unique_id(data['url'])
                if any(e.unique_id==data['url'] and (entry is None or e.entry_id!=entry.entry_id) for e in self._async_current_entries()):return self.async_abort(reason='already_configured')
                if entry is not None:
                    self.hass.config_entries.async_update_entry(entry,unique_id=data['url'],title='Buschfunk',data=data)
                    return self.async_update_reload_and_abort(entry,data_updates=data,reason='reauth_successful' if step=='reauth_confirm' else 'reconfigure_successful')
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title='Buschfunk',data=data)
            except ApiAuthError:errors['base']='invalid_auth'
            except ApiError:errors['base']='cannot_connect'
            except (ValueError,KeyError):errors['base']='invalid_url'
        return self.async_show_form(step_id=step,data_schema=schema(user_input or (entry.data if entry else None),step=='reauth_confirm'),errors=errors)

    async def async_step_user(self,user_input=None):return await self._connection(user_input,'user')
    async def async_step_reconfigure(self,user_input=None):return await self._connection(user_input,'reconfigure',self._get_reconfigure_entry())
    async def async_step_reauth(self,user_input):return await self.async_step_reauth_confirm()
    async def async_step_reauth_confirm(self,user_input=None):return await self._connection(user_input,'reauth_confirm',self._get_reauth_entry())
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):return BuschfunkOptionsFlow()

class BuschfunkOptionsFlow(OptionsFlow):
    async def async_step_init(self,user_input=None):
        if user_input is not None:return self.async_create_entry(title='',data=user_input)
        return self.async_show_form(step_id='init',data_schema=vol.Schema({vol.Required('timeout',default=self.config_entry.options.get('timeout',DEFAULT_TIMEOUT)):NumberSelector(NumberSelectorConfig(min=10,max=120,step=1,mode=NumberSelectorMode.BOX))}))
