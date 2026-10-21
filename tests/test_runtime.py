from unittest.mock import AsyncMock
from pathlib import Path
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.exceptions import ServiceValidationError,ConfigEntryAuthFailed,ConfigEntryNotReady
from custom_components.buschfunk import async_setup,async_setup_entry,async_unload_entry
from custom_components.buschfunk.api import ApiError,ApiAuthError
from custom_components.buschfunk.services import datei_laden
async def test_services_setup_unloaded_and_loaded(hass):
 await async_setup(hass,{})
 assert all(hass.services.has_service('buschfunk',s) for s in ('chats','senden','entwurf'))
 with pytest.raises(ServiceValidationError):await hass.services.async_call('buschfunk','senden',{'chat_id':1,'text':'Fixture'},blocking=True)
 e=MockConfigEntry(domain='buschfunk',data={},unique_id='fixture');e.add_to_hass(hass)
 e.runtime_data=AsyncMock();e.runtime_data.schreiben.return_value={'vorgang':'12345678-1234-4234-8234-123456789abc','angenommen':True}
 result=await hass.services.async_call('buschfunk','entwurf',{'entry_id':e.entry_id,'chat_id':1,'text':'Fixture','vorgang':'12345678-1234-4234-8234-123456789abc','benachrichtigen':True},blocking=True,return_response=True)
 assert result=={'vorgang':'12345678-1234-4234-8234-123456789abc','angenommen':True}
 e.runtime_data.schreiben.assert_awaited_once_with('entwurf',{'chatId':1,'vorgang':'12345678-1234-4234-8234-123456789abc','inhalt':{'art':'text','text':'Fixture'},'benachrichtigen':True},[])
 await async_unload_entry(hass,e)
 assert hass.services.has_service('buschfunk','entwurf')
 with pytest.raises(ServiceValidationError):await hass.services.async_call('buschfunk','senden',{'chat_id':1,'text':'Fixture'},blocking=True)
@pytest.mark.parametrize('error,want',[(ApiAuthError('invalid_auth'),ConfigEntryAuthFailed),(ApiError('cannot_connect'),ConfigEntryNotReady)])
async def test_setup_failure(hass,monkeypatch,error,want):
 monkeypatch.setattr('custom_components.buschfunk.BuschfunkApi.chats',AsyncMock(side_effect=error))
 e=MockConfigEntry(domain='buschfunk',data={'url':'https://example.com','api_key':'fixture'});e.add_to_hass(hass)
 with pytest.raises(want):await async_setup_entry(hass,e)
def test_media_symlink_and_disallowed_paths(hass,tmp_path):
 allowed=tmp_path/'allowed';allowed.mkdir();outside=tmp_path/'outside.txt';outside.write_text('private fixture')
 inside=allowed/'test.txt';inside.write_text('allowed fixture')
 link=allowed/'link.txt';link.symlink_to(outside)
 hass.config.allowlist_external_dirs={str(allowed)}
 assert datei_laden(hass,str(inside),'datei')=={'bytes':b'allowed fixture','name':'test.txt','mime':'text/plain','modus':'datei'}
 for p in [outside,link,allowed]:
  with pytest.raises(ValueError):datei_laden(hass,str(p),'datei')
 with pytest.raises(ValueError):datei_laden(hass,str(inside),'bild')

@pytest.mark.parametrize('value',[1.9,True,False,'1.9'])
async def test_registered_service_rejects_ambiguous_chat_id(hass,value):
 import voluptuous as vol
 await async_setup(hass,{})
 e=MockConfigEntry(domain='buschfunk',data={},unique_id='fixture');e.add_to_hass(hass)
 e.runtime_data=AsyncMock()
 with pytest.raises(vol.Invalid):
  await hass.services.async_call('buschfunk','senden',{'chat_id':value,'text':'Fixture'},blocking=True)
 e.runtime_data.schreiben.assert_not_awaited()

async def test_registered_service_accepts_integral_selector_value(hass):
 await async_setup(hass,{})
 e=MockConfigEntry(domain='buschfunk',data={},unique_id='fixture');e.add_to_hass(hass)
 e.runtime_data=AsyncMock()
 await hass.services.async_call('buschfunk','senden',{'chat_id':1.0,'text':'Fixture'},blocking=True)
 assert e.runtime_data.schreiben.await_args.args[1]['chatId']==1
