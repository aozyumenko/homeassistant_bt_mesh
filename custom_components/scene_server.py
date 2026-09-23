"""BT Mesh Scene Server implementation"""
from __future__ import annotations


from typing import Union
from uuid import UUID
from collections import OrderedDict

from bluetooth_mesh.utils import ParsedMeshMessage
from bluetooth_mesh.messages.scene import SceneOpcode, SceneStatusCode
from bluetooth_mesh.models.scene import SceneServer

from .const import BT_MESH_EVENT, BT_MESH_EVENT_TYPE_SCENE_RECALL

import logging
_LOGGER = logging.getLogger(__name__)


class SceneRecallDuplicateFilter:
    """ Checks whether the packet is a duplicate. """

    def __init__(self, max_size: int = 128):
        self.max_size = max_size
        self._cache = OrderedDict()

    def is_duplicate(self, source: int, tid: int) -> bool:
        key = (source, tid)

        if key in self._cache:
            self._cache.move_to_end(key)
            return True

        if len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)

        self._cache[key] = True
        return False


class SceneServerMixin:
    # self.elements
    # self.loop

    scene_filter = SceneRecallDuplicateFilter()

    def scene_server_init(self):
        """Scene Server message handlers."""

        def receive_get(
            _source: int,
            _app_index: int,
            _destination: Union[int, UUID],
            message: ParsedMeshMessage,
        ):
            server = self.elements[0][SceneServer]
            self.loop.create_task(
                server.scene_status(
                    _source,
                    _app_index,
                    SceneStatusCode.SUCCESS,
                    0
                )
            )

        def receive_register_get(
            _source: int,
            _app_index: int,
            _destination: Union[int, UUID],
            message: ParsedMeshMessage,
        ):
            server = self.elements[0][SceneServer]
            self.loop.create_task(
                server.scene_register_status(
                    _source,
                    _app_index,
                    SceneStatusCode.SUCCESS,
                    0,
                    []
                )
            )

        def receive_recall(
            _source: int,
            _app_index: int,
            _destination: Union[int, UUID],
            message: ParsedMeshMessage,
        ):
            if message.opcode == SceneOpcode.SCENE_RECALL:
                data = message.scene_recall
            elif message.opcode == SceneOpcode.SCENE_RECALL_UNACKNOWLEDGED:
                data = message.scene_recall_unacknowledged
            else:
                return

            if not self.scene_filter.is_duplicate(_source, data.tid):
                event = {
                    "type": BT_MESH_EVENT_TYPE_SCENE_RECALL,
                    "source": f"{_source:04x}",
                    "destination": f"{_destination:04x}",
                    "scene_number": data.scene_number,
                    "transition_time": data.transition_time if "transition_time" in data else 0.0,
                    "delay": data.delay if "delay" in data else 0.0
                }
                self.hass.bus.async_fire(
                    BT_MESH_EVENT,
                    event
                )

            if message.opcode == SceneOpcode.SCENE_RECALL:
                server = self.elements[0][SceneServer]
                self.loop.create_task(
                    server.scene_status(
                        _source,
                        _app_index,
                        SceneStatusCode.SUCCESS,
                        0,
                        data.scene_number,
                        0
                    )
                )

        server = self.elements[0][SceneServer]
        server.app_message_callbacks[SceneOpcode.SCENE_GET].add(receive_get)
        server.app_message_callbacks[SceneOpcode.SCENE_REGISTER_GET].add(receive_register_get)
        server.app_message_callbacks[SceneOpcode.SCENE_RECALL].add(receive_recall)
        server.app_message_callbacks[SceneOpcode.SCENE_RECALL_UNACKNOWLEDGED].add(receive_recall)
