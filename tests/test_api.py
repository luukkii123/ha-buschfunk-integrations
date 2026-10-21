import asyncio
from unittest.mock import AsyncMock,MagicMock
import aiohttp
import pytest
from custom_components.buschfunk.api import BuschfunkApi,ApiAuthError,ApiError,normalize_url
@pytest.mark.parametrize('url',['ftp://example.com','https://example@example.com','https://example.com/?key=x','https://example.com/#x','https://example.com/api','https://example.com/../'])
def test_invalid_url(url):
 with pytest.raises(ValueError):normalize_url(url)
def test_url_normalization():
 assert normalize_url(' https://EXAMPLE.com:443/ ')=='https://example.com'
@pytest.mark.parametrize('status,err',[(401,ApiAuthError),(403,ApiAuthError),(302,ApiError),(500,ApiError)])
async def test_http_errors_do_not_follow_redirects(status,err):
 session=MagicMock();response=AsyncMock();response.status=status
 session.request.return_value.__aenter__.return_value=response
 api=BuschfunkApi(session,'https://example.com','fictional-key')
 with pytest.raises(err):await api.chats()
 assert session.request.call_args.kwargs['allow_redirects'] is False
async def test_chat_response_contract():
 session=MagicMock();r=AsyncMock();r.status=200;r.json.return_value={'chats':[{'id':1,'name':'Fixture','dienst':'matrix','typ':'person'}],'naechste':None}
 session.request.return_value.__aenter__.return_value=r
 assert await BuschfunkApi(session,'https://example.com','fixture').chats()==r.json.return_value
 r.json.return_value={'chats':'wrong'}
 with pytest.raises(ApiError):await BuschfunkApi(session,'https://example.com','fixture').chats()
async def test_network_retry_keeps_payload_uuid():
 session=MagicMock();r=AsyncMock();r.status=201;r.json.return_value={'vorgang':'12345678-1234-4234-8234-123456789abc','angenommen':True}
 first=MagicMock();first.__aenter__=AsyncMock(side_effect=aiohttp.ClientConnectionError())
 second=MagicMock();second.__aenter__=AsyncMock(return_value=r)
 session.request.side_effect=[first,second]
 payload={'chatId':1,'vorgang':'12345678-1234-4234-8234-123456789abc','inhalt':{'art':'text','text':'Fixture'}}
 assert (await BuschfunkApi(session,'https://example.com','fixture').schreiben('senden',payload))['angenommen'] is True
 assert session.request.call_args_list[0].kwargs['json']==session.request.call_args_list[1].kwargs['json']==payload
async def test_unexpected_write_response_rejected():
 session=MagicMock();r=AsyncMock();r.status=201;r.json.return_value={'angenommen':True,'vorgang':'other'}
 session.request.return_value.__aenter__.return_value=r
 with pytest.raises(ApiError):await BuschfunkApi(session,'https://example.com','fixture').schreiben('senden',{'vorgang':'fixture'})
