"""BT MESH switch integration"""
from __future__ import annotations

import asyncio

from construct import Container

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.const import Platform

from bluetooth_mesh.messages.generic.onoff import GenericOnOffOpcode
from bluetooth_mesh.models.generic.onoff import GenericOnOffClient

from bt_mesh_ctrl import BtMeshModelId
from bt_mesh_ctrl.mesh_cfgclient_conf import MeshCfgModel

from .application import BtMeshApplication
from .entity import BtMeshEntity
from .const import (
    BT_MESH_DISCOVERY_ENTITY_NEW,
    G_SEND_INTERVAL,
    G_TIMEOUT,
)

import logging
_LOGGER = logging.getLogger(__name__)



async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigType,
    add_entities: AddEntitiesCallback
) -> None:
    """Set up the measuring sensor entry."""

    @callback
    def async_add_switch(
        app: BtMeshApplication,
        cfg_model: MeshCfgModel,
        passive: bool
    ) -> None:
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

    status_opcodes = (
        GenericOnOffOpcode.GENERIC_ONOFF_STATUS,
    )

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

    async def query_model_state(self) -> any:
        """Query GenericOnOff state."""
        return await self.app.generic_onoff_get(
            destination=self.unicast_addr,
            app_index=self.app_key,
        )

    async def async_update(self):
        """Extract switch state from GenericOnOff model state."""
        if self.model_state is not None:
            if "target_onoff" in self.model_state and \
                    "remaining_time" in self.model_state and \
                    self.model_state.remaining_time > 0:
                self._attr_is_on = self.model_state.target_onoff
            else:
                self._attr_is_on = self.model_state.present_onoff
        else:
            self._attr_is_on = None

        self._attr_available = self._attr_is_on is not None

    async def generic_onoff_set(self, onoff:int, transition_time:float=None) -> None:
        """Set GenericOnOff state"""
        result = await self.app.generic_onoff_set(
            destination=self.unicast_addr,
            app_index=self.app_key,
            onoff=onoff,
            transition_time=transition_time,
        )
        if result is not None:
            self.update_model_state(result)
        else:
            self.update_model_state(Container(present_onoff=1 if onoff else 0))
        self.invalidate_device_state()

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        await self.generic_onoff_set(1)

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        await self.generic_onoff_set(0)
