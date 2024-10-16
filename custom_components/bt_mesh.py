"""Bluetooth Mesh Client implementation"""
from __future__ import annotations


import sys
import time
from datetime import datetime, timedelta, timezone
import asyncio
from enum import IntEnum

from bluetooth_mesh.application import Application, Element, Capabilities
from bluetooth_mesh.messages.config import GATTNamespaceDescriptor
from bluetooth_mesh.messages.generic.onoff import GenericOnOffOpcode
from bluetooth_mesh.messages.sensor import SensorOpcode, SensorSetupOpcode
from bluetooth_mesh.models import (
    ConfigClient,
    HealthClient,
)
from bluetooth_mesh.models.generic.onoff import GenericOnOffClient
from bluetooth_mesh.models.generic.level import GenericLevelClient
from bluetooth_mesh.models.generic.dtt import GenericDTTClient
from bluetooth_mesh.models.generic.ponoff import GenericPowerOnOffClient
from bluetooth_mesh.models.sensor import SensorServer, SensorSetupServer, SensorClient
from bluetooth_mesh.models.scene import SceneClient
from bluetooth_mesh.models.light.lightness import LightLightnessClient
from bluetooth_mesh.models.light.ctl import LightCTLClient
from bluetooth_mesh.models.light.hsl import LightHSLClient
from bluetooth_mesh.models.vendor.thermostat import ThermostatClient
from bluetooth_mesh.models.time import TimeServer, TimeSetupServer

from bluetooth_mesh.messages.properties import PropertyID
from bluetooth_mesh.messages.vendor.thermostat import ThermostatOpcode, ThermostatSubOpcode
from bluetooth_mesh.messages.time import TimeOpcode, TimeRole, CURRENT_TAI_UTC_DELTA

from .const import (
    DEFAULT_DBUS_APP_PATH,
    G_SEND_INTERVAL,
    G_TIMEOUT,
    G_MESH_SENSOR_CACHE_TIMEOUT,
)

import logging
_LOGGER = logging.getLogger(__name__)



class IntEnumName(IntEnum):
    @classmethod
    def has_value(_class, val: int):
        return val in _class._value2member_map_

    @classmethod
    def get_name(_class, val: int):
        return _class(val).name if _class.has_value(val) else "%04x" % (val)


class BtMeshModelId(IntEnumName):
    """ BT Mesh model names. """
    GenericOnOffServer = 0x1000
    GenericPowerOnOffServer = 0x1006
    GenericPowerOnOffSetupServer = 0x1007
    SensorServer = SensorServer.MODEL_ID[1],
    SensorSetupServer = SensorSetupServer.MODEL_ID[1],
    SensorClient = SensorClient.MODEL_ID[1],
    LightLightnessServer = 0x1300
    LightLightnessSetupServer = 0x1301
    LightCTLServer = 0x1303
    LightCTLSetupServer = 0x1304
    LightCTLTemperatureServer = 0x1306
    LightHSLServer = 0x1307
    LightHSLSetupServer = 0x1308
    LightHSLHueServer = 0x130a
    LightHSLSaturationServer = 0x130b


class BtSensorAttrPropertyId(IntEnumName):
    """ BT Mesh sensor property names """
    PRECISE_TOTAL_DEVICE_ENERGY_USE = PropertyID.PRECISE_TOTAL_DEVICE_ENERGY_USE
    PRESENT_DEVICE_INPUT_POWER = PropertyID.PRESENT_DEVICE_INPUT_POWER
    PRESENT_INPUT_CURRENT = PropertyID.PRESENT_INPUT_CURRENT
    PRESENT_INPUT_VOLTAGE = PropertyID.PRESENT_INPUT_VOLTAGE



# BT Mesh Client Application

class MainElement(Element):
    LOCATION = GATTNamespaceDescriptor.MAIN
    MODELS = [
        ConfigClient,
        HealthClient,
        GenericOnOffClient,
        GenericDTTClient,
        GenericPowerOnOffClient,
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


    # TODO: add comment
    _sensor_cache: dict


    def __init__(self, path, token=None):
        """Initialize bluetooth_mesh application."""
        loop = asyncio.get_event_loop()
        super().__init__(loop)

        self.PATH = path
        self.TOKEN = token

        # FixMe: callback interface to separetly class
        self.pin_cb = None

        self._event_loop = None

        self._sensor_cache = dict()



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


    # Switch

    def onoff_init_receive_status(self):
        def receive_status(
            _source: int,
            _app_index: int,
            _destination: Union[int, UUID],
            message: ParsedMeshMessage,
        ):
            _LOGGER.debug("receive %04x->%04x %s" % (_source, _destination, message))

        client = self.elements[0][GenericOnOffClient]
        client.app_message_callbacks[GenericOnOffOpcode.GENERIC_ONOFF_STATUS].add(receive_status)


    async def mesh_generic_onoff_get(self, address, app_index):
        """Get GenericOnOff state"""
        client = self.elements[0][GenericOnOffClient]

        result = await client.get([address], app_index=app_index, send_interval=G_SEND_INTERVAL, timeout=G_TIMEOUT)
        return result[address].present_onoff != 0


    async def mesh_generic_onoff_set(self, address, app_index, state):
        """Set GenericOnOff state"""
        client = self.elements[0][GenericOnOffClient]
        #_LOGGER.debug("mesh_generic_onoff_set(): started")
        await client.set([address], app_index=app_index, onoff=state, transition_time=0.0, send_interval=G_SEND_INTERVAL, timeout=G_TIMEOUT)
        #_LOGGER.debug("mesh_generic_onoff_set(): finished")


    # LightLightness
    async def mesh_light_lightness_set(self, address, app_index, lightness):
        """Set LightLightness lightness"""
        client = self.elements[0][LightLightnessClient]
        await client.set([address], app_index=app_index, lightness=lightness, transition_time=0.0, send_interval=G_SEND_INTERVAL, timeout=G_TIMEOUT)


    async def mesh_light_ctl_get(self, address, app_index):
        """Get LightCTL state"""
        client = self.elements[0][LightCTLClient]
        result = await client.get([address], app_index=app_index, send_interval=G_SEND_INTERVAL, timeout=G_TIMEOUT)
        return result[address]

    async def mesh_light_ctl_set(self, address, app_index, lightness, temperature):
        """Set LightCTL temperature"""
        client = self.elements[0][LightCTLClient]
        await client.set_unack(address,
                               app_index=app_index,
                               ctl_lightness=lightness,
                               ctl_temperature=temperature,
                               ctl_delta_uv=0,
                               transition_time=0.0)

    async def mesh_light_ctl_temperature_range_get(self, address, app_index):
        """Get LightCTL temperature range"""
        client = self.elements[0][LightCTLClient]
        result = await client.temperature_range_get([address], app_index=app_index, send_interval=G_SEND_INTERVAL, timeout=G_TIMEOUT)
        return result[address]


    async def mesh_light_hsl_get(self, address, app_index):
        """Get LightHSL state"""
        client = self.elements[0][LightHSLClient]
        result = await client.get([address], app_index=app_index, send_interval=G_SEND_INTERVAL, timeout=G_TIMEOUT)
        return result[address]

    async def mesh_light_hsl_set(self, address, app_index, lightness, hue, saturation):
        """Set LightHSL lightness, hue and saturation"""
        client = self.elements[0][LightHSLClient]
        await client.set_unack(address, app_index=app_index,
                               hsl_lightness=lightness,
                               hsl_hue=hue,
                               hsl_saturation=saturation,
                               transition_time=0.0)


    # Sensor

    def sensor_init_receive_status(self):
        def receive_status(
            _source: int,
            _app_index: int,
            _destination: Union[int, UUID],
            message: ParsedMeshMessage,
        ):
            #_LOGGER.debug("receive %04x->%04x" % (_source, _destination))
            self.sensor_cache_update(_source, message['sensor_status'])

        client = self.elements[0][SensorClient]
        client.app_message_callbacks[GenericOnOffOpcode.GENERIC_ONOFF_STATUS].add(receive_status)

    def sensor_cache_update(self, addr, sensor_status):
        for property in sensor_status:
            try:
                property_id = property['sensor_setting_property_id']
                key = "%04x.%04x" % (addr, property_id)
                self._sensor_cache[key] = { 'last_update': time.time(), 'property': property }
            except Exception:
                pass

    async def sensor_descriptor_get(self, address, app_index):
        client = self.elements[0][SensorClient]
        try:
            result = await client.descriptor_get([address], app_index=app_index, send_interval=G_SEND_INTERVAL, timeout=G_TIMEOUT)
            return result[address];
        except Exception:
            _LOGGER.error("sensor_descriptor_get(): address=%04x, app_index=%d, %s" % (address, app_index, Exception))

        return None


    async def sensor_get(self, addr, app_index, property_id):
        key = "%04x.%04x" % (addr, property_id)
        line = self._sensor_cache.setdefault(key, None)

        if line == None or (line['last_update'] + G_MESH_SENSOR_CACHE_TIMEOUT) < time.time():
            client = self.elements[0][SensorClient]
            try:
                result = await client.get([addr], app_index=app_index,
                                          send_interval=G_SEND_INTERVAL, timeout=G_TIMEOUT)
                self.sensor_cache_update(addr, result[addr])
                line = self._sensor_cache.setdefault(key, None)
            except Exception:
                _LOGGER.error("failed to get Sensor, addr: %04x, app_index: %d %s" %
                              (addr, app_index, Exception))
                return None

        return line['property']


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
