"""BT MESH switch integration"""
from __future__ import annotations

import asyncio

from typing import Union
from construct import Container

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.const import Platform

from .bt_mesh.entity import BtMeshEntity
from .bt_mesh import BtMeshModelId
from .bt_mesh.mesh_cfgclient_conf import MeshCfgModel
from .const import DOMAIN, BT_MESH_APPLICATION, BT_MESH_DISCOVERY_ENTITY_NEW

import logging
_LOGGER = logging.getLogger(__name__)



async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigType,
    add_entities: AddEntitiesCallback
) -> None:
    """Set up the measuring sensor entry."""

    # FIXME: drop?
    app = hass.data[DOMAIN][config_entry.entry_id][BT_MESH_APPLICATION]

    @callback
    def async_add_switch(
        app: BtMeshApplication,
        cfg_model: MeshCfgModel,
        passive: bool
    ) -> None:
#        _LOGGER.debug(f"async_add_switch(): uuid={cfg_model.device.uuid}, model_id={cfg_model.model_id}, addr={cfg_model.unicast_addr:04x}, app_key={cfg_model.app_key}")
        add_entities([BtMeshSwitch_GenericOnOff(app, cfg_model, passive)])


    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            BT_MESH_DISCOVERY_ENTITY_NEW.format(Platform.SWITCH),
            async_add_switch,
        )
    )

    return True


class BtMeshSwitch_GenericOnOff(BtMeshEntity, SwitchEntity):
    """Representation of an Bluetooth Mesh Generic On/Off service."""

    def __init__(
        self,
        app: BtMeshApplication,
        cfg_model: MeshCfgModel,
        passive: bool
    ) -> None:
        if cfg_model.model_id != BtMeshModelId.GenericOnOffServer:
            raise ValueError("cfg_model.model_id must be GenericOnOffServer")

        BtMeshEntity.__init__(self, app, cfg_model, passive)
        self._attr_available = False

    async def async_update(self):
        """Request the device to update its status."""
        state = await self.app.generic_onoff_get(
            self.cfg_model.unicast_addr,
            self.cfg_model.app_key
        )
        if state is not None:
            if "target_onoff" in state and "remaining_time" in state and state.remaining_time > 0:
                self._attr_is_on = state.target_onoff
            else:
                self._attr_is_on = state.present_onoff
        else:
            self._attr_is_on = None

        self._attr_available = self._attr_is_on is not None
#        _LOGGER.debug(f"Get GenericOnOff state on {self.cfg_model.unicast_addr:04x}: {self._attr_is_on}, avail {self._attr_available}")

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        await self.app.generic_onoff_set(
            self.cfg_model.unicast_addr,
            self.cfg_model.app_key,
            1
        )

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        await self.app.generic_onoff_set(
            self.cfg_model.unicast_addr,
            self.cfg_model.app_key,
            0
        )
