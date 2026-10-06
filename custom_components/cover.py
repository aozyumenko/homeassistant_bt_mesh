"""BT MESH cover integration"""
from __future__ import annotations

from typing import Any, Union
from uuid import UUID

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.const import Platform
from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverEntity,
    CoverEntityFeature,
)

from bluetooth_mesh.utils import ParsedMeshMessage
from bluetooth_mesh.messages.generic.level import GenericLevelOpcode

from bt_mesh_ctrl import BtMeshModelId
from bt_mesh_ctrl.mesh_cfgclient_conf import MeshCfgModel

from .application import BtMeshApplication
from .entity import BtMeshEntity
from .const import (
    BT_MESH_DISCOVERY_ENTITY_NEW,
    CONF_UPDATE_TIME,
    CONF_KEEPALIVE_TIME,
    G_MESH_CACHE_UPDATE_TIMEOUT,
    G_MESH_CACHE_INVALIDATE_TIMEOUT,
)

import logging
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigType,
    add_entities: AddEntitiesCallback
) -> None:
    """Set up the cover entry."""

    @callback
    def async_add_cover(
        app: BtMeshApplication,
        cfg_model: MeshCfgModel,
        node_conf: dict
    ) -> None:
        platform_conf = node_conf.get(Platform.COVER, None) or {}
        update_timeout = platform_conf.get(
            CONF_UPDATE_TIME,
            node_conf.get(CONF_UPDATE_TIME, G_MESH_CACHE_UPDATE_TIMEOUT)
        )
        invalidate_timeout = platform_conf.get(
            CONF_KEEPALIVE_TIME,
            node_conf.get(CONF_KEEPALIVE_TIME, G_MESH_CACHE_INVALIDATE_TIMEOUT)
        )

        add_entities(
            [
                BtMeshSwitch_GenericLevel(
                    app=app,
                    cfg_model=cfg_model,
                    update_timeout=update_timeout,
                    invalidate_timeout=invalidate_timeout
                )
            ]
        )

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            BT_MESH_DISCOVERY_ENTITY_NEW.format(BtMeshModelId.GenericLevelServer),
            async_add_cover,
        )
    )

    return True


class BtMeshSwitch_GenericLevel(BtMeshEntity, CoverEntity):
    """Representation of an Bluetooth Mesh Generic Level service."""

    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.SET_POSITION
    )

    status_opcodes = (
        GenericLevelOpcode.GENERIC_LEVEL_STATUS,
    )

    def cover_position_to_generic_level(self, cover_position: int) -> int:
        """Converts the Cover Position (0–100) to a Generic Level (-32768–32767)."""
        cover_position = max(0, min(100, cover_position))
        return -32768 + int((cover_position / 100.0) * 65535)

    def generic_level_to_cover_position(self, generic_level: int) -> int:
        """Converts the Generic Level back to an Cover Position (0–100)."""
        generic_level = max(-32768, min(32767, generic_level))
        return int(round(((generic_level + 32768) / 65535.0) * 100.0))

    @callback
    def receive_message(
        self,
        source: int,
        app_index: int,
        destination: Union[int, UUID],
        message: ParsedMeshMessage
    ):
        """Receive status reports from GenericLevel model."""
        match message.opcode:
            case GenericLevelOpcode.GENERIC_LEVEL_STATUS:
                state = message.generic_level_status
                if "target_level" in state and \
                        "remaining_time" in state and \
                        state.remaining_time > 0:
                    cover_position = self.generic_level_to_cover_position(state.target_level)
                else:
                    cover_position = self.generic_level_to_cover_position(state.present_level)
                self._attr_is_closed = cover_position == 0
                self._attr_current_cover_position = cover_position
                self._attr_available = True
                self.async_write_ha_state()
            case _:
                pass
        super().receive_message(source, app_index, destination, message)

    async def query_model_state(self) -> any:
        """Query GenericLevel state."""
        return await self.app.generic_level_get(
            destination=self.unicast_addr,
            app_index=self.app_key,
        )

    async def async_update(self) -> None:
        """Extract cover state from GenericLevel model state."""
        if self.model_state is not None:
            if "target_level" in self.model_state and \
                    "remaining_time" in self.model_state and \
                    self.model_state.remaining_time > 0:
                cover_position = self.generic_level_to_cover_position(self.model_state.target_level)
            else:
                cover_position = self.generic_level_to_cover_position(self.model_state.present_level)

            self._attr_is_closed = cover_position == 0
            self._attr_current_cover_position = cover_position
        else:
            self._attr_is_closed = None
            self._attr_current_cover_position = None

        self._attr_available = self._attr_current_cover_position is not None

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        await self.app.generic_level_set(
            destination=self.unicast_addr,
            app_index=self.app_key,
            level=self.cover_position_to_generic_level(100)
        )

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        await self.app.generic_level_set(
            destination=self.unicast_addr,
            app_index=self.app_key,
            level=self.cover_position_to_generic_level(0)
        )

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover shutter to a specific position."""
        position = kwargs[ATTR_POSITION]
        await self.app.generic_level_set(
            destination=self.unicast_addr,
            app_index=self.app_key,
            level=self.cover_position_to_generic_level(position)
        )
