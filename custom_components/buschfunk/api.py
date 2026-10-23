"""Bounded Buschfunk v1 client. Never sends the key to redirect destinations."""
from __future__ import annotations
import asyncio
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit,urlunsplit
import aiohttp

class ApiError(Exception):
    """Response cannot be confirmed; contains no upstream body or credentials."""
class ApiAuthError(ApiError):
    """API key is invalid or revoked."""
class ApiForbiddenError(ApiAuthError):
    """Key is valid but lacks this right (e.g. an MCP key for service rooms)."""
class ApiRateLimitError(ApiError):
    """HTTP 429; retry_after holds the server's Retry-After seconds when given."""
    def __init__(self,retry_after:int|None):
        super().__init__('rate_limited');self.retry_after=retry_after

def retry_after(value:str|None)->int|None:
    # Buschfunk sends whole seconds; an HTTP date or garbage is not guessed at.
    if value is None or not value.strip().isdigit():return None
    return min(int(value.strip()),86400)

def ist_dienstraum(d)->bool:
    return isinstance(d,dict) and isinstance(d.get('kennung'),str) and isinstance(d.get('name'),str) and isinstance(d.get('archiviert'),bool) and (d.get('chatId') is None or isinstance(d['chatId'],int) and not isinstance(d['chatId'],bool))

def normalize_url(value: str) -> str:
    url = urlsplit(value.strip())
    if url.scheme not in ('http','https') or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('','/'):
        raise ValueError('invalid_url')
    port=url.port
    host=url.hostname.lower()
    if ':' in host:host=f'[{host}]'
    netloc=host if port is None or (url.scheme,port) in (('https',443),('http',80)) else f'{host}:{port}'
    return urlunsplit((url.scheme,netloc,'','',''))

class BuschfunkApi:
    def __init__(self,session:aiohttp.ClientSession,url:str,key:str,timeout:int=45):
        self.session=session;self.url=normalize_url(url);self._key=key;self.timeout=timeout

    async def _request(self,method:str,path:str,leer:bool=False,**kwargs:Any)->dict:
        try:
            async with self.session.request(method,self.url+'/api/integration/v1/'+path,headers={'Authorization':'Bearer '+self._key},timeout=aiohttp.ClientTimeout(total=self.timeout),allow_redirects=False,**kwargs) as response:
                if response.status==401:raise ApiAuthError('invalid_auth')
                if response.status==403:raise ApiForbiddenError('forbidden')
                if response.status==429:raise ApiRateLimitError(retry_after(response.headers.get('Retry-After')))
                if not 200<=response.status<300:raise ApiError(f'http_{response.status}')
                if leer:return {}
                data=await response.json()
                if not isinstance(data,dict):raise ApiError('invalid_response')
                return data
        except (aiohttp.ClientError,asyncio.TimeoutError,ValueError) as err:
            raise ApiError('cannot_connect') from err

    async def chats(self,**params:Any)->dict:
        data=await self._request('GET','chats',params=params)
        if not isinstance(data.get('chats'),list) or not all(isinstance(c,dict) and isinstance(c.get('id'),int) and not isinstance(c['id'],bool) and c['id']>0 and isinstance(c.get('name'),str) and c.get('typ') in ('person','gruppe') for c in data['chats']) or (data.get('naechste') is not None and (not isinstance(data['naechste'],int) or isinstance(data['naechste'],bool) or data['naechste']<0)):
            raise ApiError('invalid_response')
        return data

    async def schreiben(self,modus:str,payload:dict,files:list[dict]|None=None)->dict:
        path='nachrichten' if modus=='senden' else 'entwuerfe'
        for attempt in range(2):
            try:
                if files:
                    form=aiohttp.FormData()
                    form.add_field('auftrag',json.dumps(payload))
                    form.add_field('modi',json.dumps([f['modus'] for f in files]))
                    for f in files:form.add_field('datei',f['bytes'],filename=f['name'],content_type=f['mime'])
                    data=await self._request('POST',path,data=form)
                else:data=await self._request('POST',path,json=payload)
                if data.get('angenommen') is not True or data.get('vorgang')!=payload['vorgang']:raise ApiError('invalid_response')
                return data
            except ApiError as err:
                if attempt or str(err) not in ('cannot_connect','http_502','http_503','http_504'):raise
        raise ApiError('cannot_connect')

    async def dienstraeume(self)->dict:
        data=await self._request('GET','dienstraeume')
        if not isinstance(data.get('dienstraeume'),list) or not all(ist_dienstraum(d) for d in data['dienstraeume']):raise ApiError('invalid_response')
        return data

    async def _wiederholt(self,method:str,path:str,payload:dict)->dict:
        # One identical retry: PUT is idempotent, POST carries the same vorgang.
        for attempt in range(2):
            try:return await self._request(method,path,json=payload)
            except ApiError as err:
                if attempt or str(err) not in ('cannot_connect','http_502','http_504'):raise
        raise ApiError('cannot_connect')

    async def dienstraum_sicherstellen(self,kennung:str,payload:dict)->dict:
        data=await self._wiederholt('PUT','dienstraeume/'+kennung,payload)
        if not ist_dienstraum(data) or data['kennung']!=kennung or not isinstance(data.get('neu'),bool):raise ApiError('invalid_response')
        return data

    async def dienstraum_senden(self,kennung:str,payload:dict)->dict:
        data=await self._wiederholt('POST',f'dienstraeume/{kennung}/nachrichten',payload)
        if data.get('kennung')!=kennung or data.get('vorgang')!=payload['vorgang'] or not isinstance(data.get('ereignisId'),str):raise ApiError('invalid_response')
        return data

    async def dienstraum_entfernen(self,kennung:str)->None:
        # No retry: a repeated DELETE after a lost 204 would report 404.
        await self._request('DELETE','dienstraeume/'+kennung,leer=True)
