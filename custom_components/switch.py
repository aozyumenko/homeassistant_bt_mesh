"""BT MESH switch integration"""
from __future__ import annotations

import asyncio
import logging

from typing import Union

from homeassistant.core import HomeAssistant
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import BtMeshEntity
from .const import DOMAIN, BT_MESH_APPLICATION, BT_MESH_CFGCLIENT_CONF
from .bt_mesh import BtMeshModelId
from .mesh_cfgclient_conf import ELEMENT_MAIN



_LOGGER = logging.getLogger(__name__)



async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigType,
    add_entities: AddEntitiesCallback
) -> None:
    """Set up the measuring sensor entry."""

    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    application = entry_data[BT_MESH_APPLICATION]
    mesh_cfgclient_conf = hass.data[DOMAIN][BT_MESH_CFGCLIENT_CONF]

#    _LOGGER.debug("async_setup_entry(): config_entry: %s, entry_data=%s, application=%s" % (config_entry.data, entry_data, application))
#    _LOGGER.debug("async_setup_entry(): devices=%s" % (mesh_cfgclient_conf.devices))

    entities = []
    devices = mesh_cfgclient_conf.devices
    for device in devices:
        try:
            device_unicat_addr = device['unicastAddress']
            for generic_onoff in device['models'][BtMeshModelId.GenericOnOffServer]:
                element_idx = generic_onoff[ELEMENT_MAIN]
                element_unicast_addr = device_unicat_addr + element_idx
                app_key = device['app_keys'][element_idx][BtMeshModelId.GenericOnOffServer]
                _LOGGER.debug("uuid=%s, %d, addr=0x%04x, app_key=%d" % (device['UUID'], element_idx, element_unicast_addr, app_key))
                entities.append(
                    BtMeshSwitch_GenericOnOff(
                        application=application,
                        uuid=device['UUID'],
                        cid=device['cid'],
                        pid=device['pid'],
                        vid=device['vid'],
                        addr=element_unicast_addr,
                        model_id=BtMeshModelId.GenericOnOffServer,
                        app_index=app_key
                    )
                )
        except KeyError:
            continue

    add_entities(entities)

    return True



class BtMeshSwitch_GenericOnOff(BtMeshEntity, SwitchEntity):
    """Representation of an Bluetooth Mesh Generic On/Off service."""

    _state_on_off: Union[None, bool] = None
    _on_off_lock = asyncio.Lock()

    #async def async_added_to_hass(self):
    #    """Register device notification."""
        #await self.async_initialize_device(self._ads_var, pyads.PLCTYPE_BOOL)
    #    pass



    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._state_on_off is not None


    @property
    def is_on(self) -> bool:
        """Return True if the entity is on."""
        if self._state_on_off is not None:
            return self._state_on_off
        else:
            return False


    async def async_update(self):
        """Request the device to update its status."""
        async with self._on_off_lock:
            try:
                self._state_on_off = await self.application.mesh_generic_onoff_get(
                    self.unicast_addr,
                    self.app_index
                )
            except Exception:
                _LOGGER.debug("failed to get OnOff status: addr %04x, app_index %d" %
                              (self.unicast_addr, self.app_index))
                self._state_on_off = None


    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        async with self._on_off_lock:
            await self.application.mesh_generic_onoff_set(self.unicast_addr, self.app_index, 1)


    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        async with self._on_off_lock:
            await self.application.mesh_generic_onoff_set(self.unicast_addr, self.app_index, 0)
