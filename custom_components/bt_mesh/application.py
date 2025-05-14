"""BT Mesh Client Application"""
from __future__ import annotations


import asyncio
from construct import Container
import time
from datetime import datetime, timedelta, timezone

from bluetooth_mesh.application import Application, Element, Capabilities
from bluetooth_mesh.messages.config import GATTNamespaceDescriptor
from bluetooth_mesh.messages.time import TimeOpcode, TimeRole, CURRENT_TAI_UTC_DELTA
from bluetooth_mesh.messages.generic.onoff import GenericOnOffOpcode
from bluetooth_mesh.messages.generic.battery import GenericBatteryOpcode
from bluetooth_mesh.messages.light.lightness import LightLightnessOpcode
from bluetooth_mesh.messages.light.ctl import LightCTLOpcode
from bluetooth_mesh.messages.light.hsl import LightHSLOpcode
from bluetooth_mesh.messages.sensor import SensorOpcode, SensorSetupOpcode
from bluetooth_mesh.messages.vendor.thermostat import (
    ThermostatOpcode,
    ThermostatSubOpcode,
    ThermostatMode,
    ThermostatStatusCode
)

from bluetooth_mesh.models import ConfigClient, HealthClient
from bluetooth_mesh.models.generic.onoff import GenericOnOffClient
from bluetooth_mesh.models.generic.level import GenericLevelClient
from bluetooth_mesh.models.generic.dtt import GenericDTTClient
from bluetooth_mesh.models.generic.ponoff import GenericPowerOnOffClient
from bluetooth_mesh.models.generic.battery import GenericBatteryClient
from bluetooth_mesh.models.sensor import SensorServer, SensorSetupServer, SensorClient
from bluetooth_mesh.models.scene import SceneClient
from bluetooth_mesh.models.light.lightness import LightLightnessClient
from bluetooth_mesh.models.light.ctl import LightCTLClient
from bluetooth_mesh.models.light.hsl import LightHSLClient
from bluetooth_mesh.models.vendor.thermostat import ThermostatClient
from bluetooth_mesh.models.time import TimeServer, TimeSetupServer

from . import BtMeshModelId

from ..const import (
    DEFAULT_DBUS_APP_PATH,
    G_SEND_INTERVAL,
    G_TIMEOUT,
    G_UNACK_RETRANSMISSIONS,
    G_UNACK_INTERVAL,
    G_MESH_SENSOR_CACHE_TIMEOUT,
    G_MESH_CACHE_UPDATE_TIMEOUT,
    G_MESH_CACHE_INVALIDATE_TIMEOUT,
)

import logging
_LOGGER = logging.getLogger(__name__)



class MainElement(Element):
    LOCATION = GATTNamespaceDescriptor.MAIN
    MODELS = [
        ConfigClient,
        HealthClient,
        GenericOnOffClient,
        GenericDTTClient,
        GenericPowerOnOffClient,
        GenericBatteryClient,
        SceneClient,
        GenericLevelClient,
        SensorClient,
        LightLightnessClient,
        LightCTLClient,
        LightHSLClient,
        ThermostatClient,
        TimeServer,
        TimeSetupServer
    ]


class BtMeshApplication(Application):
    COMPANY_ID = 0x05f1  # Linux Foundation
    PRODUCT_ID = 0x4148  # HA - HomeAssistant
    VERSION_ID = 1
    ELEMENTS = {
        0: MainElement,
    }
    CAPABILITIES = [Capabilities.OUT_NUMERIC]

    CRPL = 32768
    PATH = DEFAULT_DBUS_APP_PATH
    TOKEN = None

    _cache: dict

    def __init__(self, path, token=None):
        """Initialize bluetooth_mesh application."""
        loop = asyncio.get_event_loop()
        super().__init__(loop)

        self.PATH = path
        self.TOKEN = token

        # FixMe: callback interface to separetly class
        self.pin_cb = None

        self._event_loop = None

        self._cache = dict()

        self._lock = asyncio.Lock()


    ##################################################
    def display_numeric(self, type: str, number: int):
        """...."""
        if self.pin_cb:
            self.pin_cb._cb_display_numeric(type, number)

    async def mesh_join(self, pin_cb=None):
        """...."""
        self.pin_cb = pin_cb
        async with self:
            token = await self.join()
        return token
    ##########################################


    # cache
    def cache_get(self, address, model_id, extra_key=None) -> (bool, any):
        if address in self._cache:
            line_address = self._cache[address]
            key = "%x_%s" % (model_id, str(extra_key))
            if line_address is not None and key in line_address:
                line = line_address[key]
                if line is not None and 'last_update' in line and 'data' in line and (line['last_update'] + G_MESH_CACHE_INVALIDATE_TIMEOUT) >= time.time():
                    valid = (line['last_update'] + G_MESH_CACHE_UPDATE_TIMEOUT) >= time.time()
                    return (valid, line['data'])

        return (False, None)

    def cache_update(self, address, model_id, data, extra_key=None):
        if not address in self._cache:
            self._cache[address] = dict()
        key = "%x_%s" % (model_id, str(extra_key))
        self._cache[address][key] = { 'last_update': time.time(), 'data': data }

    def cache_invalidate(self, address, model_id, extra_key=None):
        if model_id is None:
            self._cache[address] = dict()
        else:
            key = "%x_%s" % (model_id, str(extra_key))
            if address in self._cache and key in self._cache[address]:
                self._cache[address][key] = None

    async def cache_proxy(self, address, model_id, async_def_get, extra_key=None):
        (valid, line) = self.cache_get(address, model_id, extra_key=extra_key)
        if valid and line is not None:
            return line
        else:
            async with self._lock:
                try:
                    _result = await async_def_get
                    result = _result[address]
                    #_LOGGER.debug("cache_proxy(): request %s" % (result))
                except Exception:
                    result = None

            if result is not None:
                self.cache_update(address, model_id, result, extra_key=extra_key)
                return result
            elif line is not None:
                return line
            else:
                return None


    # Scheduller
    async def _task_sched_routine(self, hass):
        while True:
            # process Set queue

            # process Get queue

            #_LOGGER.debug("Mesh Application scheduller task...");
            await asyncio.sleep(5)

    def sched_start(self, hass):
        hass.loop.create_task(self._task_sched_routine(hass))


    # Time Server

    def time_server_init(self):

        # Time Server message handlers
        def receive_get(
            _source: int,
            _app_index: int,
            _destination: Union[int, UUID],
            message: ParsedMeshMessage,
        ):
            _LOGGER.debug("Time Get: receive %04x->%04x" % (_source, _destination))

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
            _LOGGER.debug("Time Zone Get: receive %04x->%04x" % (_source, _destination))

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
            _LOGGER.debug("TAI-UTC Delta Get: receive %04x->%04x" % (_source, _destination))

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
            _LOGGER.debug("Get: receive %04x->%04x" % (_source, _destination))

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





    # Switch
    def generic_onoff_init_receive_status(self) -> None:
        def receive_status(
            _source: int,
            _app_index: int,
            _destination: Union[int, UUID],
            message: ParsedMeshMessage,
        ):
#            _LOGGER.debug("receive %04x->%04x %s" % (_source, _destination, message))
            self.cache_update(
                _source,
                BtMeshModelId.GenericOnOffServer,
                message.generic_onoff_status
            )

        client = self.elements[0][GenericOnOffClient]
        client.app_message_callbacks[GenericOnOffOpcode.GENERIC_ONOFF_STATUS].add(receive_status)

    async def generic_onoff_get(self, address, app_index) -> Container | None:
        """Get GenericOnOff state"""
        client = self.elements[0][GenericOnOffClient]
        return await self.cache_proxy(
            address,
            BtMeshModelId.GenericOnOffServer,
            client.get(
                [address],
                app_index=app_index,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT,
            ),
            extra_key=ThermostatSubOpcode.THERMOSTAT_RANGE_STATUS
        )

    async def generic_onoff_set(self, address, app_index, state) -> None:
        """Set GenericOnOff state"""
        client = self.elements[0][GenericOnOffClient]
        async with self._lock:
            await client.set(
                [address],
                app_index=app_index,
                onoff=state,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT
            )
        self.cache_invalidate(address, None)

    # LightLightness
    def light_lightness_init_receive_status(self) -> None:
        def receive_status(
            _source: int,
            _app_index: int,
            _destination: Union[int, UUID],
            message: ParsedMeshMessage,
        ):
            self.cache_update(
                _source,
                BtMeshModelId.LightLightnessSetupServer,
                message.light_lightness_status
            )

        client = self.elements[0][LightLightnessClient]
        client.app_message_callbacks[LightLightnessOpcode.LIGHT_LIGHTNESS_STATUS].add(receive_status)

    async def light_lightness_get(self, address, app_index) -> Container | None:
        """Get LightLightness state"""
        client = self.elements[0][LightLightnessClient]
        return await self.cache_proxy(
            address,
            BtMeshModelId.LightLightnessSetupServer,
            client.get(
                [address],
                app_index=app_index,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT
            )
        )

    async def light_lightness_set(self, address, app_index, lightness) -> None:
        """Set LightLightness lightness"""
        client = self.elements[0][LightLightnessClient]
        async with self._lock:
            await client.set(
                [address],
                app_index=app_index,
                lightness=lightness,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT
            )
        self.cache_invalidate(address, None)


    # LightCTL
    def light_ctl_init_receive_status(self):
        def receive_status(
            _source: int,
            _app_index: int,
            _destination: Union[int, UUID],
            message: ParsedMeshMessage,
        ) -> None:
            self.cache_update(
                _source,
                BtMeshModelId.LightCTLSetupServer,
                message.light_ctl_status,
                extra_key=LightCTLOpcode.LIGHT_CTL_STATUS
            )

        def receive_temperature_range_status(
            _source: int,
            _app_index: int,
            _destination: Union[int, UUID],
            message: ParsedMeshMessage,
        ) -> Container | None:
            self.cache_update(
                _source,
                BtMeshModelId.LightCTLSetupServer,
                message.light_ctl_temperature_range_status,
                extra_key=LightCTLOpcode.LIGHT_CTL_TEMPERATURE_RANGE_STATUS
            )

        client = self.elements[0][LightLightnessClient]
        client.app_message_callbacks[LightCTLOpcode.LIGHT_CTL_STATUS].add(receive_status)
        client.app_message_callbacks[LightCTLOpcode.LIGHT_CTL_TEMPERATURE_RANGE_STATUS].add(receive_temperature_range_status)

    async def light_ctl_get(self, address, app_index) -> Container | None:
        """Get LightCTL state"""
        client = self.elements[0][LightCTLClient]
        return await self.cache_proxy(
            address,
            BtMeshModelId.LightCTLSetupServer,
            client.get(
                [address],
                app_index=app_index,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT
            ),
            extra_key=LightCTLOpcode.LIGHT_CTL_STATUS
        )

    async def light_ctl_set(self, address, app_index, lightness, temperature) -> None:
        """Set LightCTL state"""
        client = self.elements[0][LightCTLClient]
        async with self._lock:
            await client.set(
                [address],
                app_index=app_index,
                ctl_lightness=lightness,
                ctl_temperature=temperature,
                ctl_delta_uv=0,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT
            )
        self.cache_invalidate(address, None)

    async def light_ctl_temperature_range_get(self, address, app_index) -> Container | None:
        """Get LightCTL temperature range"""
        client = self.elements[0][LightCTLClient]
        return await self.cache_proxy(
            address,
            BtMeshModelId.LightCTLSetupServer,
            client.temperature_range_get(
                [address],
                app_index=app_index,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT
            ),
            extra_key=LightCTLOpcode.LIGHT_CTL_TEMPERATURE_RANGE_STATUS
        )


    # LightHSL
    def light_hsl_init_receive_status(self) -> None:
        def receive_status(
            _source: int,
            _app_index: int,
            _destination: Union[int, UUID],
            message: ParsedMeshMessage,
        ):
            self.cache_update(
                _source,
                BtMeshModelId.LightHSLSetupServer,
                message.light_hsl_status
            )

        client = self.elements[0][LightHSLClient]
        client.app_message_callbacks[LightHSLOpcode.LIGHT_HSL_STATUS].add(receive_status)

    async def light_hsl_get(self, address, app_index) -> Container | None:
        """Get LightHSL state"""
        client = self.elements[0][LightHSLClient]
        return await self.cache_proxy(
            address,
            BtMeshModelId.LightHSLSetupServer,
            client.get(
                [address],
                app_index=app_index,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT
            )
        )

    async def light_hsl_set(self, address, app_index, lightness, hue, saturation) -> None:
        """Set LightHSL lightness, hue and saturation"""
        client = self.elements[0][LightHSLClient]
        async with self._lock:
            await client.set(
                [address],
                app_index=app_index,
                hsl_lightness=lightness,
                hsl_hue=hue,
                hsl_saturation=saturation,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT
            )
        self.cache_invalidate(address, None)


    # Sensor
    def sensor_init_receive_status(self) -> None:
        def receive_status(
            _source: int,
            _app_index: int,
            _destination: Union[int, UUID],
            message: ParsedMeshMessage,
        ):
#            _LOGGER.debug("SENSOR_STATUS receive %04x->%04x" % (_source, _destination))
#            _LOGGER.debug(message)
            self.cache_update(
                _source,
                BtMeshModelId.SensorServer,
                message.sensor_status
            )

        client = self.elements[0][SensorClient]
        client.app_message_callbacks[SensorOpcode.SENSOR_STATUS].add(receive_status)

    async def sensor_descriptor_get(self, address, app_index) -> Container | None:
        client = self.elements[0][SensorClient]
        try:
            result = await client.descriptor_get(
                [address],
                app_index=app_index,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT)
            return result[address];
        except Exception:
            _LOGGER.error("sensor_descriptor_get(): address=%04x, app_index=%d, %s" % (address, app_index, Exception))

        return None

    async def sensor_get(self, address, app_index, property_id) -> Container | None:
        client = self.elements[0][SensorClient]
        result = await self.cache_proxy(
            address,
            BtMeshModelId.SensorServer,
            client.get(
                [address],
                app_index=app_index,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT,
            )
        )
        if result is not None:
            for property in result:
                if property_id == property.sensor_setting_property_id:
                    return property
        return None


    # Generic Battery
    def generic_battery_init_receive_status(self) -> None:
        def receive_status(
            _source: int,
            _app_index: int,
            _destination: Union[int, UUID],
            message: ParsedMeshMessage,
        ):
            self.cache_update(
                _source,
                BtMeshModelId.GenericBatteryServer,
                message.generic_battery_status
            )

        client = self.elements[0][GenericBatteryClient]
        client.app_message_callbacks[GenericBatteryOpcode.GENERIC_BATTERY_STATUS].add(receive_status)

    async def generic_battery_get(self, address, app_index) -> Container | None:
        """Get GenericBattery state"""
        client = self.elements[0][GenericBatteryClient]
        return await self.cache_proxy(
            address,
            BtMeshModelId.GenericBatteryServer,
            client.get(
                [address],
                app_index=app_index,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT,
            )
        )


    # Vendor Thermostat
    def thermostat_init_receive_status(self) -> None:
        def receive_status(
            _source: int,
            _app_index: int,
            _destination: Union[int, UUID],
            message: ParsedMeshMessage,
        ):
            vendor_message = message['vendor_thermostat']
            if vendor_message.subopcode == ThermostatSubOpcode.THERMOSTAT_STATUS:
                if vendor_message.thermostat_status.status_code == ThermostatStatusCode.GOOD:
                    self.cache_update(
                        _source,
                        BtMeshModelId.ThermostatServer,
                        vendor_message.thermostat_status,
                        extra_key=ThermostatSubOpcode.THERMOSTAT_STATUS
                )
            elif vendor_message.subopcode == ThermostatSubOpcode.THERMOSTAT_RANGE_STATUS:
                self.cache_update(
                    _source,
                    BtMeshModelId.ThermostatServer,
                    vendor_message.thermostat_range_status,
                    extra_key=ThermostatSubOpcode.THERMOSTAT_RANGE_STATUS
                )

        client = self.elements[0][ThermostatClient]
        client.app_message_callbacks[ThermostatOpcode.VENDOR_THERMOSTAT].add(receive_status)

    async def thermostat_get(self, address, app_index) -> Container | None:
        """Get Vendor Thermostat state"""
        client = self.elements[0][ThermostatClient]
        return await self.cache_proxy(
            address,
            BtMeshModelId.ThermostatServer,
            client.get(
                [address],
                app_index=app_index,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT,
            ),
            extra_key=ThermostatSubOpcode.THERMOSTAT_STATUS
        )

    async def thermostat_range_get(self, address, app_index) -> Container | None:
        """Get Vendor Thermostat range"""
        client = self.elements[0][ThermostatClient]
        return await self.cache_proxy(
            address,
            BtMeshModelId.ThermostatServer,
            client.range_get(
                [address],
                app_index=app_index,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT,
            ),
            extra_key=ThermostatSubOpcode.THERMOSTAT_RANGE_STATUS
        )

    async def thermostat_set(self, address, app_index, onoff, temperature) -> None:
        """Get Vendor Thermostat state"""
        client = self.elements[0][ThermostatClient]

        async with self._lock:
            await client.set(
                [address],
                app_index=app_index,
                onoff=onoff,
                mode=ThermostatMode.MANUAL,
                temperature=temperature,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT,
            )
            self.cache_invalidate(
                address,
                BtMeshModelId.ThermostatServer,
                extra_key=ThermostatSubOpcode.THERMOSTAT_STATUS
            )
