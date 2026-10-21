"""Native HA actions for all supported message content, without YAML payloads."""
from __future__ import annotations
from datetime import datetime
import mimetypes
from pathlib import Path
import re
from uuid import UUID,uuid4
import voluptuous as vol
from homeassistant.core import HomeAssistant,SupportsResponse,ServiceCall,callback
from homeassistant.exceptions import ServiceValidationError,Unauthorized
from .api import ApiError,ApiAuthError
from .const import DOMAIN

KINDS=('text','medien','abstimmung','standort','kontakt','ereignis')

def integer(value,minimum=1,maximum=None):
    if not isinstance(value,int) or isinstance(value,bool) or value<minimum or maximum is not None and value>maximum:raise ValueError('invalid_number')
    return value

def text(value,maxlen=20000,empty=False):
    if not isinstance(value,str) or len(value)>maxlen or not empty and not value.strip():raise ValueError('invalid_text')
    return value

def zeit(value):
    if not isinstance(value,str):raise ValueError('invalid_time')
    dt=datetime.fromisoformat(value.replace('Z','+00:00'))
    if dt.tzinfo is None:raise ValueError('invalid_time')
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

@callback
def async_register_services(hass:HomeAssistant)->None:
    for action,schema in [('chats',CHAT),('senden',WRITE),('entwurf',DRAFT)]:
        async def handle(call:ServiceCall,action=action):
            if call.context.user_id:
                user=await hass.auth.async_get_user(call.context.user_id)
                if user is None or not user.is_admin:raise Unauthorized()
            entries=[e for e in hass.config_entries.async_entries(DOMAIN) if getattr(e,'runtime_data',None) is not None and (not call.data.get('entry_id') or e.entry_id==call.data['entry_id'])]
            if len(entries)!=1:raise ServiceValidationError(translation_domain=DOMAIN,translation_key='select_entry')
            entry=entries[0];api=entry.runtime_data
            payload=None
            try:
                if action=='chats':return await api.chats(**{k:v for k,v in call.data.items() if k!='entry_id'})
                payload=baue_auftrag(action,call.data)
                files=[]
                for path in call.data.get('dateien',[]):
                    files.append(await hass.async_add_executor_job(datei_laden,hass,path,call.data.get('medienmodus','datei')))
                    if sum(len(f['bytes']) for f in files)>100*1024*1024:raise ValueError('file_too_large')
                return await api.schreiben(action,payload,files)
            except ApiAuthError as err:
                entry.async_start_reauth(hass)
                raise ServiceValidationError(translation_domain=DOMAIN,translation_key='invalid_auth') from err
            except (ValueError,OSError) as err:
                raise ServiceValidationError(translation_domain=DOMAIN,translation_key='invalid_content') from err
            except ApiError as err:
                raise ServiceValidationError(translation_domain=DOMAIN,translation_key='request_failed',translation_placeholders={'vorgang':payload['vorgang'] if payload else '-'}) from err
        hass.services.async_register(DOMAIN,action,handle,schema=vol.Schema(schema),supports_response=SupportsResponse.ONLY if action=='chats' else SupportsResponse.OPTIONAL)
