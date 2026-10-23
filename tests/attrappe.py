"""Buschfunk API stand-in on 127.0.0.1 following the core's service-room rules (#503)."""
import base64,re
from aiohttp import web
from aiohttp.test_utils import TestServer

KEY='fixture-key'
KENNUNG=re.compile(r'[a-z0-9](?:[a-z0-9_-]{0,30}[a-z0-9])?')

class Attrappe:
    def __init__(self,dienstraeume=True):
        self.raeume={};self.anfragen=[];self.nachrichten=[];self.stoerung=[];self.dienstraeume=dienstraeume
        app=web.Application(middlewares=[self.waechter])
        app.router.add_get('/api/integration/v1/chats',self.chats)
        if dienstraeume:
            app.router.add_get('/api/integration/v1/dienstraeume',self.liste)
            app.router.add_put('/api/integration/v1/dienstraeume/{kennung}',self.sicherstellen)
            app.router.add_post('/api/integration/v1/dienstraeume/{kennung}/nachrichten',self.senden)
            app.router.add_delete('/api/integration/v1/dienstraeume/{kennung}',self.entfernen)
        self.server=TestServer(app,host='127.0.0.1')
    @property
    def url(self):return str(self.server.make_url('/')).rstrip('/')
    async def __aenter__(self):await self.server.start_server();return self
    async def __aexit__(self,*a):await self.server.close()
    def dienst_anfragen(self):return [a for a in self.anfragen if '/dienstraeume' in a[1]]

    @web.middleware
    async def waechter(self,request,handler):
        body=await request.json() if request.can_read_body else None
        self.anfragen.append((request.method,request.path,body))
        auth=request.headers.get('Authorization')
        if auth=='Bearer mcp-key' and '/dienstraeume' in request.path:return web.json_response({'fehler':'Kein Recht.'},status=403)
        if auth not in ('Bearer '+KEY,'Bearer mcp-key'):return web.json_response({'fehler':'Schlüssel fehlt.'},status=401)
        # Like the core's integration guard: paths it does not know are 403, not 404.
        if request.match_info.http_exception is not None:return web.json_response({'fehler':'Nicht freigegeben.'},status=403)
        if self.stoerung:
            status,headers=self.stoerung.pop(0)
            return web.json_response({'fehler':'Störung'},status=status,headers=headers)
        request['body']=body
        return await handler(request)

    async def chats(self,request):return web.json_response({'chats':[],'naechste':None})
    async def liste(self,request):
        return web.json_response({'dienstraeume':[dict(r) for r in self.raeume.values()],'grenze':20})
    async def sicherstellen(self,request):
        k=request.match_info['kennung'];b=request['body']
        if not KENNUNG.fullmatch(k) or not isinstance(b,dict) or set(b)-{'name','bild'} or not isinstance(b.get('name'),str) or not b['name'].strip() or len(b['name'].strip())>64:
            return web.json_response({'fehler':'Eingabe'},status=400)
        if 'bild' in b and len(base64.b64decode(b['bild']))>1024*1024:return web.json_response({'fehler':'groß'},status=413)
        neu=k not in self.raeume
        if neu and len(self.raeume)>=20:return web.json_response({'fehler':'voll'},status=409)
        r=self.raeume.setdefault(k,{'kennung':k,'chatId':100+len(self.raeume),'archiviert':False,'erstelltUm':'2026-10-23T08:00:00.000Z'})
        r['name']=b['name'].strip()
        return web.json_response({**r,'neu':neu},status=201 if neu else 200)
    async def senden(self,request):
        k=request.match_info['kennung'];b=request['body']
        if set(b)-{'text','titel','wichtig','vorgang'} or not isinstance(b.get('text'),str) or not b['text'].strip() or len(b['text'])>4000:
            return web.json_response({'fehler':'Eingabe'},status=400)
        if k not in self.raeume:return web.json_response({'fehler':'Dienstraum nicht gefunden.'},status=404)
        if b['vorgang'] not in [n['vorgang'] for n in self.nachrichten]:self.nachrichten.append({'kennung':k,**b})
        return web.json_response({'kennung':k,'vorgang':b['vorgang'],'ereignisId':'$fixture-ereignis'},status=201)
    async def entfernen(self,request):
        if self.raeume.pop(request.match_info['kennung'],None) is None:return web.json_response({'fehler':'Dienstraum nicht gefunden.'},status=404)
        return web.Response(status=204)
