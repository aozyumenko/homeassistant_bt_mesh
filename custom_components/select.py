"""BT MESH select integration"""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.const import Platform, EntityCategory

from bt_mesh_ctrl import BtMeshModelId
from bt_mesh_ctrl.mesh_cfgclient_conf import MeshCfgModel

from .application import BtMeshApplication
from .entity import BtMeshEntity
from .const import (
    BT_MESH_DISCOVERY_ENTITY_NEW,
    CONF_UPDATE_TIME,
    CONF_KEEPALIVE_TIME,
    G_MESH_CACHE_UPDATE_LONG_TIMEOUT,
    G_MESH_CACHE_INVALIDATE_LONG_TIMEOUT,
)

import logging
_LOGGER = logging.getLogger(__name__)


POWERON_STATES = {
    "Off": 0x00,
    "On": 0x01,
    "Restore": 0x02,
}
REV_POWERON_STATES = {v: k for k, v in POWERON_STATES.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigType,
    add_entities: AddEntitiesCallback
) -> None:
    """Set up the select entry."""

    @callback
    def async_add_generic_ponoff(
        app: BtMeshApplication,
        cfg_model: MeshCfgModel,
        node_conf: dict
    ) -> None:
        """Create Generic Powr OnOff entry."""
        platform_conf = node_conf.get(Platform.SWITCH, None) or {}
        update_long_timeout = platform_conf.get(
            CONF_UPDATE_TIME,
            node_conf.get(CONF_UPDATE_TIME, G_MESH_CACHE_UPDATE_LONG_TIMEOUT)
        )
        invalidate_long_timeout = platform_conf.get(
            CONF_KEEPALIVE_TIME,
            node_conf.get(CONF_KEEPALIVE_TIME, G_MESH_CACHE_INVALIDATE_LONG_TIMEOUT)
        )

        add_entities(
            [
                BtMeshSwitch_GenericPowerOnOff(
                    app=app,
                    cfg_model=cfg_model,
                    update_timeout=update_long_timeout,
                    invalidate_timeout=invalidate_long_timeout
                )
            ]
        )

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            BT_MESH_DISCOVERY_ENTITY_NEW.format(BtMeshModelId.GenericPowerOnOffSetupServer),
            async_add_generic_ponoff,
        )
    )

    return True


class BtMeshSwitch_GenericPowerOnOff(BtMeshEntity, SelectEntity):
    """Representation of an Bluetooth Mesh Generic Power OnOff service."""

    def __init__(
        self,
        app: BtMeshApplication,
        cfg_model: MeshCfgModel,
        **kwargs: Any
    ) -> None:
        super().__init__(app, cfg_model, **kwargs)
        self._attr_translation_key = "on_power_up"
        self._attr_options = list(POWERON_STATES.keys())
        self._attr_current_option = None
        self._attr_icon = "mdi:power-settings"
        self._attr_entity_category = EntityCategory.CONFIG

    async def query_model_state(self) -> any:
        """Query GenericPowerOnOff state."""
        return await self.app.generic_ponoff_get(
            destination=self.unicast_addr,
            app_index=self.app_key,
        )

    async def async_update(self):
        """Extract switch state from GenericOnOff model state."""
        if self.model_state is None:
            self._attr_available = False
        else:
            self._attr_available = True

        if self.model_state.on_power_up in REV_POWERON_STATES:
            self._attr_current_option = REV_POWERON_STATES[self.model_state.on_power_up]


    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        on_power_up = POWERON_STATES[option]

        result = await self.app.generic_ponoff_set(
            destination=self.unicast_addr,
            app_index=self.app_key,
            on_power_up=on_power_up,
        )
        if result is not None:
            self.update_model_state(result)
        else:
            self.update_model_state(Container(on_power_up=on_power_up))
        self.invalidate_device_state()
