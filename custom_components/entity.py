import asyncio
import time

from bluetooth_numbers import company

from homeassistant.helpers.entity import Entity, DeviceInfo
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)

from bt_mesh_ctrl import BtMeshModelId, BtMeshOpcode
from bt_mesh_ctrl.mesh_cfgclient_conf import MeshCfgModel
from bt_mesh_ctrl.product import product

from construct import Container
#from bluetooth_mesh.models.base import Model
from typing import Type         # ?????
from typing import Union
from uuid import UUID
from bluetooth_mesh.utils import ParsedMeshMessage


from .application import BtMeshApplication
from .const import (
    DOMAIN,
    G_MESH_CACHE_UPDATE_TIMEOUT,
    G_MESH_CACHE_INVALIDATE_TIMEOUT,
    BT_MESH_MSG,
    BT_MESH_INVALIDATE,
)

import logging
_LOGGER = logging.getLogger(__name__)



class ClassNotFoundError(Exception):
    """Factory could not find the class."""


class BtMeshEntity(Entity):
    """Basic representation of a BT Mesh service."""
    app: BtMeshApplication
    cfg_model: MeshCfgModel
    subs: list[([type], [int])]
    update_threshold = 0.5      # FIXME: to const
    invalidate_timeout: float = G_MESH_CACHE_INVALIDATE_TIMEOUT
    update_timeout: float = G_MESH_CACHE_UPDATE_TIMEOUT
    passive: bool

    _lock: asyncio.Lock
    _task: asyncio.Task
    _last_update: [float | None]
    _model_state: any

    def __init__(
        self,
        app: BtMeshApplication,
        cfg_model: MeshCfgModel,
        passive: bool = False
    ) -> None:
        """Initialize model entity."""
        self.app = app
        self.cfg_model = cfg_model
        self.passive = passive

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(self.cfg_model.device.unique_id))},
            name=f"{DOMAIN}_{self.cfg_model.device.unicast_addr:04x}",
            manufacturer=company[self.cfg_model.device.cid] \
                if self.cfg_model.device.cid in company \
                    else f"{self.cfg_model.device.cid:04x}",
            model=product[(self.cfg_model.device.vid, self.cfg_model.device.pid)] \
                if (self.cfg_model.device.vid, self.cfg_model.device.pid) in product \
                    else f"{self.cfg_model.device.vid:04x}:{self.cfg_model.device.pid:04x}",
            model_id=f"{self.cfg_model.device.vid:04x}:{self.cfg_model.device.pid:04x}",
            sw_version=f"{self.cfg_model.device.vid:04x}",
        )
        self._attr_unique_id = self.cfg_model.unique_id
        self._attr_name = self.cfg_model.name

        self._lock = asyncio.Lock()
        self._task = None

        self._last_update = None
        self._model_state = None

        if hasattr(self, 'status_opcodes'):
            for opcode in self.status_opcodes:
                async_dispatcher_connect(
                    app.hass,
                    BT_MESH_MSG.format(self.unicast_addr, opcode),
                    self.receive_message,
                )

        async_dispatcher_connect(
            app.hass,
            BT_MESH_INVALIDATE.format(self.unicast_addr),
            self.invalidate_model_state,
        )

    def receive_message(
        self,
        source: int,
        app_index: int,
        destination: Union[int, UUID],
        message: ParsedMeshMessage
    ):
        opcode_name = BtMeshOpcode.get(message.opcode).name.lower()
        #self.update_model_state_thr(message[opcode_name])
        self.update_model_state(message[opcode_name])

    @property
    def unicast_addr(self) -> int:
        return self.cfg_model.unicast_addr

    @property
    def app_key(self) -> int:
        return self.cfg_model.app_key

    @property
    def model_id(self) -> BtMeshModelId:
        return self.cfg_model.model_id

    @property
    def model_state(self) -> any:
        if self._last_update is not None and (self._last_update + self.invalidate_timeout) >= time.time():
            valid = (self._last_update + self.update_timeout) >= time.time()
            if not valid and not self.passive:
                self._query_model_state()
            return self._model_state

        self._query_model_state()
        return None

    def update_model_state(self, state: any):
        self._last_update = time.time()
        self._model_state = state
        self.schedule_update_ha_state()

#    def update_model_state_thr(self, state: any):
#        async def _set_value_after_delay(state: any):
#            try:
#                _LOGGER.debug(f"_set_value_after_delay():  {self.unicast_addr:04x}.{self.property_id:04x} start")
#                await asyncio.sleep(self.update_threshold)
#                self.update_model_state(state)
#                _LOGGER.debug(f"Update model state {self.name}: {repr(self._model_state)} [{self._last_update:f}]")
#            except asyncio.CancelledError:
#                _LOGGER.debug(f"_set_value_after_delay():  {self.unicast_addr:04x}.{self.property_id:04x} cancel")
#                pass
#
#        if self._task is not None:
#            self._task.cancel()
#        self._task = self.app.loop.create_task(_set_value_after_delay(state))
#        _LOGGER.debug(f"update_model_state(): {self.unicast_addr:04x}, state={state}")

    def _query_model_state(self):
        async def query_model_state_task():
            async with self._lock:
                state = await self.query_model_state()
                _LOGGER.debug(f"Get {self.name} state: {repr(state)} [{time.time():f}]")
                if state is not None:
                    self.update_model_state(state)

        if not self.passive:
            if not self._lock.locked():
                _LOGGER.debug(f"Querye model state {self.name}")
                self.app.hass.create_task(query_model_state_task())

    async def query_model_state(self) -> any:
        return None

    def invalidate_model_state(self):
        _LOGGER.debug(f"Invalidate model state {self.name}")
        self._last_update = time.time() - self.update_timeout
        self._query_model_state()

    def invalidate_device_state(self):
        async_dispatcher_send(
            self.app.hass,
            BT_MESH_INVALIDATE.format(self.unicast_addr),
        )
