from unittest.mock import AsyncMock
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.buschfunk.api import ApiAuthError,ApiError
@pytest.fixture(autouse=True)
def setup(monkeypatch):
 monkeypatch.setattr('custom_components.buschfunk.async_setup_entry',AsyncMock(return_value=True))
 monkeypatch.setattr('custom_components.buschfunk.async_unload_entry',AsyncMock(return_value=True))
@pytest.mark.parametrize('failure,error',[(ApiAuthError('invalid_auth'),'invalid_auth'),(ApiError('cannot_connect'),'cannot_connect')])
async def test_config_error_recovery(hass,monkeypatch,failure,error):
 probe=AsyncMock(side_effect=failure);monkeypatch.setattr('custom_components.buschfunk.config_flow.validate',probe)
 r=await hass.config_entries.flow.async_init('buschfunk',context={'source':'user'})
 r=await hass.config_entries.flow.async_configure(r['flow_id'],{'url':'https://example.com/','api_key':'fixture'})
 assert r['errors']=={'base':error}
 probe.side_effect=None
 r=await hass.config_entries.flow.async_configure(r['flow_id'],{'url':'https://example.com/','api_key':'fixture'})
 assert r['type']=='create_entry';assert r['result'].unique_id=='https://example.com'
 assert r['data']=={'url':'https://example.com','api_key':'fixture'}
async def test_duplicate(hass,monkeypatch):
 monkeypatch.setattr('custom_components.buschfunk.config_flow.validate',AsyncMock())
 MockConfigEntry(domain='buschfunk',unique_id='https://example.com',data={'url':'https://example.com','api_key':'fixture'}).add_to_hass(hass)
 r=await hass.config_entries.flow.async_init('buschfunk',context={'source':'user'})
 r=await hass.config_entries.flow.async_configure(r['flow_id'],{'url':'https://example.com/','api_key':'fixture'})
 assert r['reason']=='already_configured'
async def test_reconfigure_reauth_and_options(hass,monkeypatch):
 monkeypatch.setattr('custom_components.buschfunk.config_flow.validate',AsyncMock())
 e=MockConfigEntry(domain='buschfunk',unique_id='https://example.com',data={'url':'https://example.com','api_key':'fixture'});e.add_to_hass(hass)
 r=await hass.config_entries.flow.async_init('buschfunk',context={'source':'reconfigure','entry_id':e.entry_id})
 r=await hass.config_entries.flow.async_configure(r['flow_id'],{'url':'https://example.net','api_key':'new-fixture'})
 assert r['reason']=='reconfigure_successful';assert e.data['url']=='https://example.net'
 r=await hass.config_entries.flow.async_init('buschfunk',context={'source':'reauth','entry_id':e.entry_id},data=e.data)
 r=await hass.config_entries.flow.async_configure(r['flow_id'],{'api_key':'replacement-fixture'})
 assert r['reason']=='reauth_successful';assert e.data['api_key']=='replacement-fixture'
 r=await hass.config_entries.options.async_init(e.entry_id)
 r=await hass.config_entries.options.async_configure(r['flow_id'],{'timeout':60})
 assert r['type']=='create_entry';assert e.options=={'timeout':60}
