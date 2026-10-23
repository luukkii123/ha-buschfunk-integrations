import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError,ServiceValidationError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from custom_components.buschfunk.api import BuschfunkApi,ApiAuthError,ApiForbiddenError,ApiRateLimitError,ApiError,retry_after
from custom_components.buschfunk.services import zeit,baue_dienstraum_nachricht
from attrappe import Attrappe,KEY

UUID='12345678-1234-4234-8234-123456789abc'
# The stand-in is a real HTTP server on 127.0.0.1; HA's test plugin blocks sockets by default.
pytestmark=pytest.mark.usefixtures('socket_enabled')
PNG=b'\x89PNG\r\n\x1a\n'+b'\0'*32

@pytest.fixture
async def attrappe():
 async with Attrappe() as a:yield a

async def einrichten(hass,a,key=KEY):
 e=MockConfigEntry(domain='buschfunk',title='Buschfunk',unique_id=a.url,data={'url':a.url,'api_key':key});e.add_to_hass(hass)
 await hass.config_entries.async_setup(e.entry_id);await hass.async_block_till_done()
 return e

def sensor(hass):
 from homeassistant.helpers import entity_registry as er
 reg=er.async_get(hass)
 ids=[x.entity_id for x in reg.entities.values() if x.unique_id.endswith('_dienstraeume')]
 assert len(ids)==1
 return hass.states.get(ids[0])

# --- API client against the stand-in ---

async def test_api_round_trip(hass,attrappe):
 api=BuschfunkApi(async_get_clientsession(hass),attrappe.url,KEY)
 r=await api.dienstraum_sicherstellen('waschmaschine',{'name':'Waschmaschine'})
 assert r['neu'] is True and r['name']=='Waschmaschine'
 assert (await api.dienstraum_sicherstellen('waschmaschine',{'name':'Waschmaschine'}))['neu'] is False
 r=await api.dienstraum_senden('waschmaschine',{'text':'Fertig','vorgang':UUID})
 assert r=={'kennung':'waschmaschine','vorgang':UUID,'ereignisId':'$fixture-ereignis'}
 assert [d['kennung'] for d in (await api.dienstraeume())['dienstraeume']]==['waschmaschine']
 assert await api.dienstraum_entfernen('waschmaschine') is None
 assert (await api.dienstraeume())['dienstraeume']==[]

@pytest.mark.parametrize('key,err',[('wrong',ApiAuthError),('mcp-key',ApiForbiddenError)])
async def test_api_auth_errors(hass,attrappe,key,err):
 with pytest.raises(err):await BuschfunkApi(async_get_clientsession(hass),attrappe.url,key).dienstraeume()

async def test_api_rate_limit_carries_retry_after(hass,attrappe):
 attrappe.stoerung=[(429,{'Retry-After':'17'}),(429,{})]
 api=BuschfunkApi(async_get_clientsession(hass),attrappe.url,KEY)
 with pytest.raises(ApiRateLimitError) as info:await api.dienstraum_senden('x',{'text':'x','vorgang':UUID})
 assert info.value.retry_after==17
 with pytest.raises(ApiRateLimitError) as info:await api.dienstraeume()
 assert info.value.retry_after is None
 assert len(attrappe.dienst_anfragen())==2  # 429 is never retried automatically

@pytest.mark.parametrize('value,want',[('17',17),(' 3 ',3),(None,None),('Wed, 21 Oct 2026 07:28:00 GMT',None),('-1',None),('999999',86400)])
def test_retry_after_parsing(value,want):
 assert retry_after(value)==want

async def test_api_502_retried_once_with_same_operation(hass,attrappe):
 api=BuschfunkApi(async_get_clientsession(hass),attrappe.url,KEY)
 await api.dienstraum_sicherstellen('tuer',{'name':'Haustür'})
 attrappe.stoerung=[(502,{})]
 assert (await api.dienstraum_senden('tuer',{'text':'Klingel','vorgang':UUID}))['vorgang']==UUID
 posts=[a for a in attrappe.anfragen if a[0]=='POST']
 assert len(posts)==2 and posts[0][2]==posts[1][2] and len(attrappe.nachrichten)==1

async def test_api_delete_not_retried(hass,attrappe):
 attrappe.stoerung=[(502,{})]
 with pytest.raises(ApiError):await BuschfunkApi(async_get_clientsession(hass),attrappe.url,KEY).dienstraum_entfernen('tuer')
 assert len(attrappe.dienst_anfragen())==1

# --- actions and sensor on a real config entry ---

async def test_send_with_name_and_picture_file_adds_room(hass,attrappe,tmp_path):
 bild=tmp_path/'tuer.png';bild.write_bytes(PNG);hass.config.allowlist_external_dirs={str(tmp_path)}
 await einrichten(hass,attrappe)
 assert sensor(hass).state=='0'
 r=await hass.services.async_call('buschfunk','dienstraum_senden',{'kennung':'tuer','name':' Haustür ','titel':'Klingel','text':'Es hat geklingelt.','wichtig':True,'bild':str(bild),'vorgang':UUID},blocking=True,return_response=True)
 assert r=={'kennung':'tuer','vorgang':UUID,'ereignisId':'$fixture-ereignis','neu':True}
 put,post=[a for a in attrappe.anfragen if a[0] in ('PUT','POST')]
 assert put[2]=={'name':'Haustür','bild':base64.b64encode(PNG).decode()}
 assert post[2]=={'text':'Es hat geklingelt.','titel':'Klingel','wichtig':True,'vorgang':UUID}
 await hass.async_block_till_done()
 s=sensor(hass)
 assert s.state=='1' and s.attributes['dienstraeume']==[{'kennung':'tuer','name':'Haustür','chat_id':100,'archiviert':False}] and s.attributes['grenze']==20
 await hass.services.async_call('buschfunk','dienstraum_entfernen',{'kennung':'tuer'},blocking=True)
 await hass.async_block_till_done()
 assert sensor(hass).state=='0'

async def test_send_without_name_does_not_touch_room(hass,attrappe):
 await einrichten(hass,attrappe)
 attrappe.raeume['smarthome']={'kennung':'smarthome','name':'Smart Home','chatId':5,'archiviert':False,'erstelltUm':'2026-10-23T08:00:00.000Z'}
 r=await hass.services.async_call('buschfunk','dienstraum_senden',{'kennung':'smarthome','text':'Hallo','titel':''},blocking=True,return_response=True)
 assert 'neu' not in r
 post=[a for a in attrappe.dienst_anfragen() if a[0]!='GET']
 assert len(post)==1 and post[0][2]['text']=='Hallo' and 'titel' not in post[0][2] and 'wichtig' not in post[0][2]

async def test_ensure_returns_room(hass,attrappe):
 await einrichten(hass,attrappe)
 r=await hass.services.async_call('buschfunk','dienstraum_sicherstellen',{'kennung':'waschmaschine','name':'Waschmaschine'},blocking=True,return_response=True)
 assert r['neu'] is True and r['kennung']=='waschmaschine'

LANG='x'*4001
@pytest.mark.parametrize('action,data,key',[
 ('dienstraum_senden',{'kennung':'Waschmaschine','text':'x'},'invalid_kennung'),
 ('dienstraum_senden',{'kennung':'-tuer','text':'x'},'invalid_kennung'),
 ('dienstraum_senden',{'kennung':'a'*33,'text':'x'},'invalid_kennung'),
 ('dienstraum_senden',{'kennung':'tuer','text':' '},'invalid_text'),
 ('dienstraum_senden',{'kennung':'tuer','text':LANG},'invalid_text'),
 ('dienstraum_senden',{'kennung':'tuer','text':'a\x00b'},'invalid_text'),
 ('dienstraum_senden',{'kennung':'tuer','text':'x','titel':'zwei\nZeilen'},'invalid_titel'),
 ('dienstraum_senden',{'kennung':'tuer','text':'x','titel':'t'*121},'invalid_titel'),
 ('dienstraum_senden',{'kennung':'tuer','text':'x','name':'n'*65},'invalid_name'),
 ('dienstraum_senden',{'kennung':'tuer','text':'x','bild_entitaet':'image.tuer'},'invalid_name'),
 ('dienstraum_senden',{'kennung':'tuer','text':'x','vorgang':'keine-uuid'},'invalid_content'),
 ('dienstraum_sicherstellen',{'kennung':'tuer','name':'  '},'invalid_name'),
 ('dienstraum_sicherstellen',{'kennung':'tuer','name':'T\u2028ür'},'invalid_name'),
 ('dienstraum_sicherstellen',{'kennung':'tuer','name':'\x1fTür'},'invalid_name'),
 ('dienstraum_sicherstellen',{'kennung':'tuer','name':'Tür','bild':'/a.png','bild_entitaet':'image.tuer'},'invalid_image'),
 ('dienstraum_sicherstellen',{'kennung':'tuer','name':'Tür','bild_entitaet':'sensor.tuer'},'invalid_image'),
 ('dienstraum_entfernen',{'kennung':'tür'},'invalid_kennung'),
])
async def test_limits_checked_before_any_request(hass,attrappe,action,data,key):
 await einrichten(hass,attrappe);vorher=len(attrappe.dienst_anfragen())
 with pytest.raises(ServiceValidationError) as info:await hass.services.async_call('buschfunk',action,data,blocking=True,return_response=action!='dienstraum_entfernen')
 assert info.value.translation_key==key
 assert len(attrappe.dienst_anfragen())==vorher

@pytest.mark.parametrize('inhalt,key',[(b'\x89PNG\r\n\x1a\n'+b'\0'*(1024*1024),'image_too_large'),(b'<svg/>','invalid_image')])
async def test_picture_file_checked_locally(hass,attrappe,tmp_path,inhalt,key):
 bild=tmp_path/'bild.png';bild.write_bytes(inhalt);hass.config.allowlist_external_dirs={str(tmp_path)}
 await einrichten(hass,attrappe)
 with pytest.raises(ServiceValidationError) as info:
  await hass.services.async_call('buschfunk','dienstraum_sicherstellen',{'kennung':'tuer','name':'Tür','bild':str(bild)},blocking=True,return_response=True)
 assert info.value.translation_key==key and not [a for a in attrappe.anfragen if a[0]=='PUT']

async def test_picture_file_outside_allowlist(hass,attrappe,tmp_path):
 bild=tmp_path/'bild.png';bild.write_bytes(PNG);hass.config.allowlist_external_dirs=set()
 await einrichten(hass,attrappe)
 with pytest.raises(ServiceValidationError) as info:
  await hass.services.async_call('buschfunk','dienstraum_sicherstellen',{'kennung':'tuer','name':'Tür','bild':str(bild)},blocking=True,return_response=True)
 assert info.value.translation_key=='invalid_image'

def bildquelle(monkeypatch,domain,get):
 # Stub module: the real camera component needs PyTurboJPEG, absent from the test image.
 import sys,types
 monkeypatch.setitem(sys.modules,f'homeassistant.components.{domain}',types.SimpleNamespace(async_get_image=get))

@pytest.mark.parametrize('domain',['image','camera'])
async def test_picture_from_entity(hass,attrappe,monkeypatch,domain):
 get=AsyncMock(return_value=SimpleNamespace(content_type='image/png',content=PNG))
 bildquelle(monkeypatch,domain,get)
 await einrichten(hass,attrappe)
 await hass.services.async_call('buschfunk','dienstraum_sicherstellen',{'kennung':'tuer','name':'Tür','bild_entitaet':f'{domain}.tuer'},blocking=True,return_response=True)
 get.assert_awaited_once_with(hass,f'{domain}.tuer',**({'width':512} if domain=='camera' else {}))
 assert [a for a in attrappe.anfragen if a[0]=='PUT'][0][2]['bild']==base64.b64encode(PNG).decode()

async def test_picture_entity_without_picture(hass,attrappe,monkeypatch):
 bildquelle(monkeypatch,'camera',AsyncMock(side_effect=HomeAssistantError('none')))
 await einrichten(hass,attrappe)
 with pytest.raises(ServiceValidationError) as info:
  await hass.services.async_call('buschfunk','dienstraum_sicherstellen',{'kennung':'tuer','name':'Tür','bild_entitaet':'camera.tuer'},blocking=True,return_response=True)
 assert info.value.translation_key=='image_unavailable'

async def test_rate_limit_reported_with_seconds(hass,attrappe):
 await einrichten(hass,attrappe)
 attrappe.stoerung=[(429,{'Retry-After':'42'})]
 with pytest.raises(HomeAssistantError) as info:
  await hass.services.async_call('buschfunk','dienstraum_senden',{'kennung':'tuer','text':'x'},blocking=True,return_response=True)
 assert info.value.translation_key=='rate_limited' and info.value.translation_placeholders=={'sekunden':'42'}
 assert not isinstance(info.value,ServiceValidationError)
 attrappe.stoerung=[(429,{})]
 with pytest.raises(HomeAssistantError) as info:
  await hass.services.async_call('buschfunk','dienstraum_entfernen',{'kennung':'tuer'},blocking=True)
 assert info.value.translation_key=='rate_limited_later'

@pytest.mark.parametrize('status,key',[(404,'room_not_found'),(409,'room_limit'),(413,'image_too_large'),(503,'rooms_unavailable'),(400,'invalid_content'),(500,'room_request_failed')])
async def test_server_errors_mapped(hass,attrappe,status,key):
 await einrichten(hass,attrappe)
 attrappe.stoerung=[(status,{})]
 with pytest.raises(ServiceValidationError) as info:
  await hass.services.async_call('buschfunk','dienstraum_sicherstellen',{'kennung':'tuer','name':'Tür'},blocking=True,return_response=True)
 assert info.value.translation_key==key

async def test_send_failure_names_operation(hass,attrappe):
 await einrichten(hass,attrappe)
 attrappe.raeume['tuer']={'kennung':'tuer','name':'Tür','chatId':1,'archiviert':False,'erstelltUm':'x'}
 attrappe.stoerung=[(502,{}),(502,{})]
 with pytest.raises(ServiceValidationError) as info:
  await hass.services.async_call('buschfunk','dienstraum_senden',{'kennung':'tuer','text':'x','vorgang':UUID},blocking=True,return_response=True)
 assert info.value.translation_key=='request_failed' and info.value.translation_placeholders=={'vorgang':UUID}

async def test_forbidden_key_starts_reauth_but_setup_survives(hass):
 async with Attrappe() as a:
  e=await einrichten(hass,a,key='mcp-key')
  assert e.state is ConfigEntryState.LOADED and sensor(hass).state=='unavailable'
  with pytest.raises(ServiceValidationError) as info:
   await hass.services.async_call('buschfunk','dienstraum_senden',{'kennung':'tuer','text':'x'},blocking=True,return_response=True)
  assert info.value.translation_key=='forbidden'
  # Reauth would accept the same key again (chats is allowed), so none is started.
  assert not any(f['context']['source']=='reauth' for f in hass.config_entries.flow.async_progress())

async def test_old_buschfunk_without_service_rooms(hass):
 # An older core's guard answers 403 for unknown paths; messaging keeps working.
 async with Attrappe(dienstraeume=False) as a:
  e=await einrichten(hass,a)
  assert e.state is ConfigEntryState.LOADED and sensor(hass).state=='unavailable'
  assert [x[0] for x in a.dienst_anfragen()]==['GET']
  with pytest.raises(ServiceValidationError) as info:
   await hass.services.async_call('buschfunk','dienstraum_senden',{'kennung':'tuer','text':'x'},blocking=True,return_response=True)
  assert info.value.translation_key=='forbidden'
  assert not any(f['context']['source']=='reauth' for f in hass.config_entries.flow.async_progress())
  assert await hass.config_entries.async_unload(e.entry_id)

# --- pure checks ---

def test_trim_matches_javascript():
 from custom_components.buschfunk.services import raumname
 assert raumname('\u2028 Tür\ufeff')=='Tür'
 with pytest.raises(ValueError):raumname('\x85Tür')

def test_code_point_limits_match_core():
 assert baue_dienstraum_nachricht({'text':'😀'*4000,'titel':'😀'*120,'vorgang':UUID})['text']=='😀'*4000
 assert baue_dienstraum_nachricht({'text':'Zeile 1\nZeile 2\tTab','vorgang':UUID.upper()})['vorgang']==UUID

@pytest.mark.parametrize('value',['2026-10-10T12:00:00Z','2026-10-10T12:00:00.123+02:00','2026-10-10T12:00:00-14:59'])
def test_zeit_accepts_core_format(value):
 assert isinstance(zeit(value),int)

@pytest.mark.parametrize('value',['2026-10-10','2026-10-10T12:00Z','2026-10-10T12:00+02:00','2026-10-10T12:00:00','2026-10-10 12:00:00Z','2026-02-30T12:00:00Z','2026-10-10T24:00:00Z','2026-10-10T12:00:00.1234Z','2026-10-10T12:00:00+15:00','2026-10-10T12:00:00z','2026-10-10T12:00:00+0200',None,1791633600])
def test_zeit_rejects_what_core_rejects(value):
 with pytest.raises(ValueError):zeit(value)
