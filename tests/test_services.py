import pytest
from custom_components.buschfunk.services import baue_auftrag
UUID='12345678-1234-4234-8234-123456789abc'
@pytest.mark.parametrize('fields,inhalt',[
 ({'art':'text','text':'Fixture'},{'art':'text','text':'Fixture'}),
 ({'art':'medien','dateien':['/config/fixture.txt'],'text':'Fixture'},{'art':'medien','text':'Fixture'}),
 ({'art':'abstimmung','frage':'Wann?','antworten':['Heute','Morgen'],'mehrfach':True},{'art':'abstimmung','frage':'Wann?','antworten':['Heute','Morgen'],'mehrfach':True}),
 ({'art':'standort','breite':48.2,'laenge':16.3,'name':'Fixture'},{'art':'standort','breite':48.2,'laenge':16.3,'name':'Fixture'}),
 ({'art':'kontakt','name':'Fixture','telefon':'+1234567'},{'art':'kontakt','name':'Fixture','telefon':'+1234567'}),
 ({'art':'ereignis','name':'Fixture','beginn':'2026-10-10T12:00:00Z','ende':'2026-10-10T13:00:00Z','ort':'Fixture'},{'art':'ereignis','name':'Fixture','beginn':1791633600000,'ende':1791637200000,'ort':'Fixture'}),
])
def test_all_content_types(fields,inhalt):
 assert baue_auftrag('senden',{'chat_id':1,'vorgang':UUID,**fields})=={'chatId':1,'vorgang':UUID,'inhalt':inhalt}
def test_draft_options():
 assert baue_auftrag('entwurf',{'chat_id':1,'vorgang':UUID,'art':'text','text':'Fixture','ablauf_in_sekunden':3600,'benachrichtigen':True})=={'chatId':1,'vorgang':UUID,'inhalt':{'art':'text','text':'Fixture'},'ablaufInSekunden':3600,'benachrichtigen':True}
@pytest.mark.parametrize('fields',[
 {'art':'text','text':''},{'art':'text','text':'x','chat_id':0},{'art':'standort','breite':91,'laenge':1},
 {'art':'abstimmung','frage':'x','antworten':['x','x']},{'art':'kontakt','name':'x','telefon':'no'},
 {'art':'ereignis','name':'x','beginn':'2026-10-10'}, {'art':'text','text':'x','ablauf_in_sekunden':1},
 {'art':'medien','dateien':[]},{'art':'text','text':'x','vorgang':'x'},
])
def test_invalid_content(fields):
 with pytest.raises(ValueError):baue_auftrag('senden',{'chat_id':1,**fields})
def test_expiry_exclusive():
 with pytest.raises(ValueError):baue_auftrag('entwurf',{'chat_id':1,'art':'text','text':'x','ablauf_in_sekunden':1,'verfaellt_um':'2026-10-10T12:00:00Z'})

def test_every_shipped_selector_is_valid_homeassistant_schema():
 from homeassistant.util.yaml import load_yaml
 from homeassistant.helpers.selector import validate_selector
 metadata=load_yaml('custom_components/buschfunk/services.yaml')
 def check(fields):
  for field in fields.values():
   if 'fields' in field:check(field['fields'])
   else:validate_selector(field['selector'])
 for service in metadata.values():check(service['fields'])
