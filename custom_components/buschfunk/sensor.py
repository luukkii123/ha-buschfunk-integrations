"""One sensor per instance: number of active service rooms, list as attribute."""
from __future__ import annotations
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType,DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from .coordinator import DienstraumKoordinator

PARALLEL_UPDATES=0

async def async_setup_entry(hass:HomeAssistant,entry:ConfigEntry,async_add_entities:AddConfigEntryEntitiesCallback)->None:
    async_add_entities([DienstraeumeSensor(entry.runtime_data.koordinator,entry)])

class DienstraeumeSensor(CoordinatorEntity[DienstraumKoordinator],SensorEntity):
    _attr_has_entity_name=True
    _attr_translation_key='dienstraeume'

    def __init__(self,koordinator:DienstraumKoordinator,entry:ConfigEntry):
        super().__init__(koordinator)
        self._attr_unique_id=f'{entry.entry_id}_dienstraeume'
        self._attr_device_info=DeviceInfo(identifiers={(DOMAIN,entry.entry_id)},name=entry.title,manufacturer='Buschfunk',entry_type=DeviceEntryType.SERVICE)

    @property
    def native_value(self)->int|None:
        return len(self.coordinator.data['dienstraeume']) if self.coordinator.data else None

    @property
    def extra_state_attributes(self)->dict|None:
        if not self.coordinator.data:return None
        return {'dienstraeume':[{'kennung':d['kennung'],'name':d['name'],'chat_id':d.get('chatId'),'archiviert':d['archiviert']} for d in self.coordinator.data['dienstraeume']],'grenze':self.coordinator.data.get('grenze')}
