"""BT Mesh Time Server implementation"""
from __future__ import annotations


import time
from datetime import datetime, timedelta, timezone
from typing import Union
from uuid import UUID

from bluetooth_mesh.utils import ParsedMeshMessage
from bluetooth_mesh.messages.time import (
    TimeOpcode,
    TimeRole,
    CURRENT_TAI_UTC_DELTA,
)
from bluetooth_mesh.models.time import TimeServer, TimeSetupServer

import logging
_LOGGER = logging.getLogger(__name__)



class TimeServerMixin:
    # self.elements
    # self.loop

    def time_server_init(self):
        # Time Server message handlers
        def receive_get(
            _source: int,
            _app_index: int,
            _destination: Union[int, UUID],
            message: ParsedMeshMessage,
        ):
            system_timezone_offset = time.timezone * -1
            system_timezone = timezone(offset=timedelta(seconds=system_timezone_offset))
            date = datetime.now(system_timezone)

            server = self.elements[0][TimeServer]
            self.loop.create_task(
                server.time_status(
                    _source,
                    _app_index,
                    date,
                    timedelta(seconds=CURRENT_TAI_UTC_DELTA),
                    timedelta(0),
                    True
                )
            )

        def receive_time_zone_get(
            _source: int,
            _app_index: int,
            _destination: Union[int, UUID],
            message: ParsedMeshMessage,
        ):
            system_timezone_offset = time.timezone * -1
            system_timezone_delta = timedelta(seconds=system_timezone_offset)

            server = self.elements[0][TimeServer]
            self.loop.create_task(
                server.time_zone_status(
                    _source,
                    _app_index,
                    system_timezone_delta,
                    system_timezone_delta,
                    0
                )
            )

        def receive_tai_utc_delta_get(
            _source: int,
            _app_index: int,
            _destination: Union[int, UUID],
            message: ParsedMeshMessage,
        ):
            server = self.elements[0][TimeServer]
            self.loop.create_task(
                server.tai_utc_delta_status(
                    _source,
                    _app_index,
                    CURRENT_TAI_UTC_DELTA,
                    CURRENT_TAI_UTC_DELTA,
                    0
                )
            )

        # Time Setup Server message handlers
        def receive_set(
            _source: int,
            _app_index: int,
            _destination: Union[int, UUID],
            message: ParsedMeshMessage,
        ):
            server = self.elements[0][TimeServer]
            self.loop.create_task(
                server.time_status(
                    _source,
                    _app_index,
                    message.time_set.date,
                    message.time_set.tai_utc_delta,
                    message.time_set.uncertainty,
                    message.time_set.time_authority,
                )
            )


        server = self.elements[0][TimeServer]
        server.app_message_callbacks[TimeOpcode.TIME_GET].add(receive_get)
        server.app_message_callbacks[TimeOpcode.TIME_ZONE_GET].add(receive_time_zone_get)
        server.app_message_callbacks[TimeOpcode.TAI_UTC_DELTA_GET].add(receive_tai_utc_delta_get)

        server = self.elements[0][TimeSetupServer]
        server.app_message_callbacks[TimeOpcode.TIME_SET].add(receive_set)
