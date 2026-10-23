"""Native HA actions for all supported message content, without YAML payloads."""
from __future__ import annotations
import base64
from datetime import datetime
import mimetypes
from pathlib import Path
import re
from uuid import UUID,uuid4
import voluptuous as vol
from homeassistant.core import HomeAssistant,SupportsResponse,ServiceCall,callback
from homeassistant.exceptions import HomeAssistantError,ServiceValidationError,Unauthorized
from homeassistant.helpers import config_validation as cv
from .api import ApiError,ApiAuthError,ApiForbiddenError,ApiRateLimitError
from .const import DOMAIN

KINDS=('text','medien','abstimmung','standort','kontakt','ereignis')

def integer(value,minimum=1,maximum=None):
    if not isinstance(value,int) or isinstance(value,bool) or value<minimum or maximum is not None and value>maximum:raise ValueError('invalid_number')
    return value

def text(value,maxlen=20000,empty=False):
    if not isinstance(value,str) or len(value)>maxlen or not empty and not value.strip():raise ValueError('invalid_text')
    return value

# Same shape the Buschfunk core accepts: date, time with seconds, optional
# milliseconds and a zone. fromisoformat alone also takes '2026-10-10' or
# '12:00' without seconds, which the core then rejects with HTTP 400.
ZEIT=re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?(?:Z|[+-](\d{2}):(\d{2}))')

def zeit(value):
    m=ZEIT.fullmatch(value) if isinstance(value,str) else None
    if not m or m[1] is not None and (int(m[1])>14 or int(m[2])>59) or int(value[11:13])>23:raise ValueError('invalid_time')
    dt=datetime.fromisoformat(value.replace('Z','+00:00'))
    return integer(int(dt.timestamp()*1000))

def baue_auftrag(modus:str,data:dict)->dict:
    art=data.get('art','text')
    if art not in KINDS or modus not in ('senden','entwurf'):raise ValueError('invalid_content')
    v=data.get('vorgang') or str(uuid4())
    if not isinstance(v,str) or not re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}',v):raise ValueError('invalid_uuid')
    inhalt={'art':art}
    if art in ('text','medien'):inhalt['text']=text(data.get('text',''),empty=art=='medien')
    if art=='medien':
        files=data.get('dateien')
        if not isinstance(files,list) or not 1<=len(files)<=20 or any(not isinstance(f,str) or not f for f in files):raise ValueError('invalid_files')
        if data.get('medienmodus','datei') not in ('bild','video','datei'):raise ValueError('invalid_files')
    elif data.get('dateien'):raise ValueError('invalid_files')
    if art=='abstimmung':
        answers=data.get('antworten')
        if not isinstance(answers,list) or not 2<=len(answers)<=12:raise ValueError('invalid_poll')
        answers=[text(a,100) for a in answers]
        if len(set(a.strip() for a in answers))!=len(answers) or not isinstance(data.get('mehrfach',False),bool):raise ValueError('invalid_poll')
        inhalt.update(frage=text(data.get('frage'),255),antworten=answers,mehrfach=data.get('mehrfach',False))
    if art=='standort':
        b,l=data.get('breite'),data.get('laenge')
        if not isinstance(b,(int,float)) or isinstance(b,bool) or not isinstance(l,(int,float)) or isinstance(l,bool) or not -90<=b<=90 or not -180<=l<=180 or b==l==0:raise ValueError('invalid_location')
        inhalt.update(breite=b,laenge=l)
    if art in ('kontakt','ereignis'):inhalt['name']=text(data.get('name'),512)
    elif art=='standort' and data.get('name'):inhalt['name']=text(data['name'],200)
    if art=='kontakt':
        phone=text(data.get('telefon'),64)
        if not re.fullmatch(r'\+?[0-9 ()\-./]{3,64}',phone.strip()):raise ValueError('invalid_contact')
        inhalt['telefon']=phone
    if art=='ereignis':
        inhalt['beginn']=zeit(data.get('beginn'))
        if data.get('ende'):
            inhalt['ende']=zeit(data['ende'])
            if inhalt['ende']<inhalt['beginn']:raise ValueError('invalid_time')
        for k,maxlen in [('beschreibung',20000),('ort',512)]:
            if data.get(k) is not None:inhalt[k]=text(data[k],maxlen,empty=True)
    payload={'chatId':integer(data.get('chat_id')),'vorgang':str(UUID(v)),'inhalt':inhalt}
    options=('ablauf_in_sekunden','verfaellt_um','benachrichtigen')
    if modus=='senden' and any(k in data for k in options):raise ValueError('draft_options_only')
    if modus=='entwurf':
        if 'ablauf_in_sekunden' in data and 'verfaellt_um' in data:raise ValueError('exclusive_expiry')
        if 'ablauf_in_sekunden' in data:payload['ablaufInSekunden']=integer(data['ablauf_in_sekunden'],maximum=2147483647)
        if 'verfaellt_um' in data:
            zeit(data['verfaellt_um']);payload['verfaelltUm']=data['verfaellt_um']
        if 'benachrichtigen' in data:
            if not isinstance(data['benachrichtigen'],bool):raise ValueError('invalid_boolean')
            payload['benachrichtigen']=data['benachrichtigen']
    return payload

def datei_laden(hass:HomeAssistant,path:str,modus:str)->dict:
    """Resolve symlinks before checking HA's explicit allowed path list."""
    p=Path(path).resolve(strict=True)
    if not p.is_file() or not hass.config.is_allowed_path(str(p)):raise ValueError('invalid_files')
    if p.stat().st_size>100*1024*1024:raise ValueError('file_too_large')
    mime=mimetypes.guess_type(p.name)[0] or 'application/octet-stream'
    if modus=='bild' and not mime.startswith('image/') or modus=='video' and not mime.startswith('video/'):raise ValueError('invalid_files')
    with p.open('rb') as f:content=f.read(100*1024*1024+1)
    if len(content)>100*1024*1024:raise ValueError('file_too_large')
    return {'bytes':content,'name':p.name,'mime':mime,'modus':modus}

KENNUNG=re.compile(r'[a-z0-9](?:[a-z0-9_-]{0,30}[a-z0-9])?')
STEUER=re.compile('[\x00-\x1f\x7f-\x9f\u2028\u2029]')
STEUER_TEXT=re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
# String.prototype.trim(): Python's strip() would also drop \x1c-\x1f and \x85.
JS_TRIM='\t\n\x0b\x0c\r \xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff'
BILD_MAX=1024*1024
BILD_DOMAINS=('image','camera')

def kennung(value):
    if not isinstance(value,str) or not KENNUNG.fullmatch(value):raise ValueError('invalid_kennung')
    return value

def raumname(value):
    # Python len() counts code points like the core's [...name].length.
    name=value.strip(JS_TRIM) if isinstance(value,str) else ''
    if not name or len(name)>64 or STEUER.search(name):raise ValueError('invalid_name')
    return name

def leer(value)->bool:
    return value is None or isinstance(value,str) and not value.strip(JS_TRIM)

def ist_bild(content:bytes)->bool:
    return content[:8]==b'\x89PNG\r\n\x1a\n' or content[:3]==b'\xff\xd8\xff' or content[:6] in (b'GIF87a',b'GIF89a') or content[:4]==b'RIFF' and content[8:12]==b'WEBP'

def bild_kodieren(content:bytes)->str:
    if len(content)>BILD_MAX:raise ValueError('image_too_large')
    if not ist_bild(content):raise ValueError('invalid_image')
    return base64.b64encode(content).decode('ascii')

def bild_laden(hass:HomeAssistant,path:str)->str:
    """Room picture from an allowed local file; symlinks resolved before the check."""
    p=Path(path).resolve(strict=True)
    if not p.is_file() or not hass.config.is_allowed_path(str(p)):raise ValueError('invalid_image')
    with p.open('rb') as f:content=f.read(BILD_MAX+1)
    return bild_kodieren(content)

async def bild_aus_entitaet(hass:HomeAssistant,entity_id:str)->str:
    domain=entity_id.split('.',1)[0]
    if domain not in BILD_DOMAINS:raise ValueError('invalid_image')
    # Imported on use: camera pulls in stream support HA only loads on demand.
    try:
        if domain=='image':
            from homeassistant.components.image import async_get_image
            image=await async_get_image(hass,entity_id)
        else:
            # Snapshots are often several MiB; HA scales JPEGs on a best-effort basis.
            from homeassistant.components.camera import async_get_image
            image=await async_get_image(hass,entity_id,width=512)
    except HomeAssistantError as err:raise ValueError('image_unavailable') from err
    return bild_kodieren(image.content)

def baue_dienstraum(data:dict)->dict:
    """PUT body {name, bild?}; the picture itself is loaded separately."""
    if data.get('bild') and data.get('bild_entitaet'):raise ValueError('invalid_image')
    return {'name':raumname(data.get('name'))}

def baue_dienstraum_nachricht(data:dict)->dict:
    text=data.get('text')
    if not isinstance(text,str) or not text.strip(JS_TRIM) or len(text)>4000 or STEUER_TEXT.search(text):raise ValueError('invalid_text')
    payload={'text':text}
    if not leer(data.get('titel')):
        titel=data['titel']
        if not isinstance(titel,str) or len(titel)>120 or STEUER.search(titel):raise ValueError('invalid_titel')
        payload['titel']=titel.strip(JS_TRIM)
    if 'wichtig' in data:
        if not isinstance(data['wichtig'],bool):raise ValueError('invalid_boolean')
        payload['wichtig']=data['wichtig']
    v=data.get('vorgang') or str(uuid4())
    if not isinstance(v,str) or not re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}',v):raise ValueError('invalid_uuid')
    payload['vorgang']=str(UUID(v))
    return payload

def selector_integer(value):
    # HA number selectors may emit 1.0; fractions and booleans must never change chat IDs.
    if isinstance(value,bool):raise vol.Invalid('invalid_number')
    if isinstance(value,float):
        if not value.is_integer():raise vol.Invalid('invalid_number')
    elif not isinstance(value,int) and not (isinstance(value,str) and re.fullmatch(r'[0-9]+',value)):
        raise vol.Invalid('invalid_number')
    return int(value)

def selector_float(value):
    if isinstance(value,bool):raise vol.Invalid('invalid_number')
    try:return float(value)
    except (ValueError,TypeError) as err:raise vol.Invalid('invalid_number') from err

COMMON={vol.Optional('entry_id'):str}
WRITE={**COMMON,vol.Required('chat_id'):vol.All(selector_integer,vol.Range(min=1)),vol.Optional('art',default='text'):vol.In(KINDS)}
for key in ('text','frage','name','telefon','beginn','ende','beschreibung','ort','vorgang'):WRITE[vol.Optional(key)]=str
for key in ('antworten','dateien'):WRITE[vol.Optional(key)]=[str]
for key in ('breite','laenge'):WRITE[vol.Optional(key)]=selector_float
WRITE[vol.Optional('mehrfach')]=bool
WRITE[vol.Optional('medienmodus')]=vol.In(('bild','video','datei'))
DRAFT={**WRITE,vol.Optional('ablauf_in_sekunden'):vol.All(selector_integer,vol.Range(min=1,max=2147483647)),vol.Optional('verfaellt_um'):str,vol.Optional('benachrichtigen'):bool}
CHAT={**COMMON,vol.Optional('suche'):str,vol.Optional('dienst'):str,vol.Optional('nach'):vol.All(selector_integer,vol.Range(min=0)),vol.Optional('limit'):vol.All(selector_integer,vol.Range(min=1,max=100))}
RAUM={**COMMON,vol.Required('kennung'):cv.string}
BILD={vol.Optional('bild'):cv.string,vol.Optional('bild_entitaet'):cv.entity_id}
SICHERSTELLEN={**RAUM,vol.Required('name'):cv.string,**BILD}
RAUM_SENDEN={**RAUM,vol.Optional('name'):cv.string,vol.Optional('titel'):cv.string,vol.Required('text'):cv.string,vol.Optional('wichtig'):bool,**BILD,vol.Optional('vorgang'):cv.string}

# ValueError codes with their own message; everything else is invalid_content.
EIGENE_FEHLER=('invalid_kennung','invalid_name','invalid_titel','invalid_text','invalid_image','image_too_large','image_unavailable')
API_FEHLER={'http_400':'invalid_content','http_404':'room_not_found','http_409':'room_limit','http_413':'image_too_large','http_503':'rooms_unavailable'}

async def raumbild(hass:HomeAssistant,data:dict)->str|None:
    if data.get('bild'):return await hass.async_add_executor_job(bild_laden,hass,data['bild'])
    if data.get('bild_entitaet'):return await bild_aus_entitaet(hass,data['bild_entitaet'])
    return None

async def sicherstellen(hass:HomeAssistant,api,data:dict)->dict:
    payload=baue_dienstraum(data)
    bild=await raumbild(hass,data)
    if bild:payload['bild']=bild
    return await api.dienstraum_sicherstellen(kennung(data['kennung']),payload)

async def ausfuehren(hass:HomeAssistant,action:str,api,data:dict,merke:dict):
    if action=='chats':return await api.chats(**{k:v for k,v in data.items() if k!='entry_id'})
    if action in ('senden','entwurf'):
        payload=baue_auftrag(action,data);merke['vorgang']=payload['vorgang']
        files=[]
        for path in data.get('dateien',[]):
            files.append(await hass.async_add_executor_job(datei_laden,hass,path,data.get('medienmodus','datei')))
            if sum(len(f['bytes']) for f in files)>100*1024*1024:raise ValueError('file_too_large')
        return await api.schreiben(action,payload,files)
    k=kennung(data['kennung'])
    if action=='dienstraum_sicherstellen':return await sicherstellen(hass,api,data)
    if action=='dienstraum_entfernen':return await api.dienstraum_entfernen(k)
    payload=baue_dienstraum_nachricht(data);merke['vorgang']=payload['vorgang']
    raum=None
    if not leer(data.get('name')):raum=await sicherstellen(hass,api,data)
    elif data.get('bild') or data.get('bild_entitaet'):raise ValueError('invalid_name')
    result=await api.dienstraum_senden(k,payload)
    return {**result,'neu':raum['neu']} if raum else result

AKTIONEN=[('chats',CHAT,SupportsResponse.ONLY),('senden',WRITE,SupportsResponse.OPTIONAL),('entwurf',DRAFT,SupportsResponse.OPTIONAL),
 ('dienstraum_senden',RAUM_SENDEN,SupportsResponse.OPTIONAL),('dienstraum_sicherstellen',SICHERSTELLEN,SupportsResponse.OPTIONAL),('dienstraum_entfernen',RAUM,SupportsResponse.NONE)]

@callback
def async_register_services(hass:HomeAssistant)->None:
    for action,schema,response in AKTIONEN:
        async def handle(call:ServiceCall,action=action):
            if call.context.user_id:
                user=await hass.auth.async_get_user(call.context.user_id)
                if user is None or not user.is_admin:raise Unauthorized()
            entries=[e for e in hass.config_entries.async_entries(DOMAIN) if getattr(e,'runtime_data',None) is not None and (not call.data.get('entry_id') or e.entry_id==call.data['entry_id'])]
            if len(entries)!=1:raise ServiceValidationError(translation_domain=DOMAIN,translation_key='select_entry')
            entry=entries[0];daten=entry.runtime_data
            merke={}
            try:
                result=await ausfuehren(hass,action,daten.api,dict(call.data),merke)
                # Only changes to the room list refresh the sensor, not every message.
                # Room changes are throttled to 60/h by the core, so refresh at once instead of debounced.
                if action in ('dienstraum_sicherstellen','dienstraum_entfernen') or isinstance(result,dict) and 'neu' in result:await daten.koordinator.async_refresh()
                return result
            except ApiForbiddenError as err:
                # No reauth: the reauth check (chats) passes with the same key, and an
                # older core answers 403 for every path it does not know yet.
                raise ServiceValidationError(translation_domain=DOMAIN,translation_key='forbidden') from err
            except ApiAuthError as err:
                entry.async_start_reauth(hass)
                raise ServiceValidationError(translation_domain=DOMAIN,translation_key='invalid_auth') from err
            except ApiRateLimitError as err:
                if err.retry_after is None:raise HomeAssistantError(translation_domain=DOMAIN,translation_key='rate_limited_later') from err
                raise HomeAssistantError(translation_domain=DOMAIN,translation_key='rate_limited',translation_placeholders={'sekunden':str(err.retry_after)}) from err
            except (ValueError,OSError) as err:
                key=str(err) if isinstance(err,ValueError) and str(err) in EIGENE_FEHLER else 'invalid_content'
                raise ServiceValidationError(translation_domain=DOMAIN,translation_key=key) from err
            except ApiError as err:
                if action.startswith('dienstraum') and str(err) in API_FEHLER:
                    raise ServiceValidationError(translation_domain=DOMAIN,translation_key=API_FEHLER[str(err)]) from err
                if action in ('dienstraum_sicherstellen','dienstraum_entfernen'):raise ServiceValidationError(translation_domain=DOMAIN,translation_key='room_request_failed') from err
                raise ServiceValidationError(translation_domain=DOMAIN,translation_key='request_failed',translation_placeholders={'vorgang':merke.get('vorgang','-')}) from err
        hass.services.async_register(DOMAIN,action,handle,schema=vol.Schema(schema),supports_response=response)
