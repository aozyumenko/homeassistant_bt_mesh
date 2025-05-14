"""BT MESH switch integration"""
from __future__ import annotations

import asyncio

from typing import Union
from construct import Container

from homeassistant.core import HomeAssistant
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .bt_mesh.entity import BtMeshEntity
from .const import DOMAIN, BT_MESH_APPLICATION, BT_MESH_CFGCLIENT_CONF
from .bt_mesh import BtMeshModelId
from .mesh_cfgclient_conf import ELEMENT_MAIN

import logging
_LOGGER = logging.getLogger(__name__)



async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigType,
    add_entities: AddEntitiesCallback
) -> None:
    """Set up the measuring sensor entry."""

    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    application = entry_data[BT_MESH_APPLICATION]
    mesh_cfgclient_conf = entry_data[BT_MESH_CFGCLIENT_CONF]

    entities = []
    devices = mesh_cfgclient_conf.devices
#    _LOGGER.debug("devices=%s" % (devices))
    for device in devices:
        try:
            device_unicat_addr = device['unicastAddress']
            for generic_onoff in device['models'][BtMeshModelId.GenericOnOffServer]:
                element_idx = generic_onoff[ELEMENT_MAIN]
                element_unicast_addr = device_unicat_addr + element_idx
                app_key = device['app_keys'][element_idx][BtMeshModelId.GenericOnOffServer]
#                _LOGGER.debug("uuid=%s, %d, addr=0x%04x, app_key=%d" % (device['UUID'], element_idx, element_unicast_addr, app_key))
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

    application.generic_onoff_init_receive_status()

    return True


class BtMeshSwitch_GenericOnOff(BtMeshEntity, SwitchEntity):
    """Representation of an Bluetooth Mesh Generic On/Off service."""

    _state: Union[None, Container] = None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._state is not None

    @property
    def is_on(self) -> bool:
        """Return True if the entity is on."""
        if self._state is not None and 'present_onoff' in self._state:
            return self._state.present_onoff
        else:
            return False

    async def async_update(self):
        """Request the device to update its status."""
        self._state = await self.application.generic_onoff_get(self.unicast_addr, self.app_index)

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        await self.application.generic_onoff_set(self.unicast_addr, self.app_index, 1)
        self.application.cache_invalidate(self.unicast_addr, None)

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        await self.application.generic_onoff_set(self.unicast_addr, self.app_index, 0)
        self.application.cache_invalidate(self.unicast_addr, None)
