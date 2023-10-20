"""Bluetooth Mesh Client implementation"""
from __future__ import annotations


import sys
import time
import asyncio
import logging
from enum import IntEnum

from bluetooth_mesh.application import Application, Element, Capabilities
from bluetooth_mesh.messages.config import GATTNamespaceDescriptor
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

from bluetooth_mesh.messages.properties import PropertyID

from .const import (
    DBUS_APP_PATH,
    G_TIMEOUT,
    G_MESH_SENSOR_CACHE_TIMEOUT,
)



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
        LightHSLClient
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
    PATH = DBUS_APP_PATH
    TOKEN = None

    _sensor_cache: dict


    def __init__(self, token=None):
        """Initialize bluetooth_mesh application."""
        loop = asyncio.get_event_loop()
        super().__init__(loop)

        self.TOKEN = token
        # FixMe: callback interface to separetly class
        self.pin_cb = None

        self._event_loop = None

        self._sensor_cache = dict()



    ##################################################
    def display_numeric(self, type: str, number: int):
        if self.pin_cb:
            self.pin_cb._cb_display_numeric(type, number)

    async def mesh_join(self, pin_cb=None):
        """...."""
        self.pin_cb = pin_cb
        async with self:
            token = await self.join()
        return token
    ##########################################

    # Config

    # TODO: pub_set



    # Switch

    async def mesh_generic_onoff_get(self, address, app_index):
        """Get GenericOnOff state"""
        client = self.elements[0][GenericOnOffClient]
        # FixMe: exception
        try:
            result = await client.get([address], app_index=app_index, timeout=G_TIMEOUT)
            # FixMe: check result
            #_LOGGER.error("mesh_generic_onoff_get(): address=0x%x, present_onoff=%d" % (address, result[address].present_onoff))
            return result[address].present_onoff != 0
        except Exception:
            _LOGGER.error("mesh_generic_onoff_get(): address=%04x, app_index=%d, %s" % (address, app_index, Exception))

        return False


    async def mesh_generic_onoff_set(self, address, app_index, state):
        """Set GenericOnOff state"""
        client = self.elements[0][GenericOnOffClient]
        #_LOGGER.debug("mesh_generic_onoff_set(): started")
        await client.set([address], app_index=app_index, onoff=state, transition_time=0.0, timeout=G_TIMEOUT)
        #_LOGGER.debug("mesh_generic_onoff_set(): finished")



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
        client.app_message_callbacks[SensorOpcode.SENSOR_STATUS].add(receive_status)


    def sensor_cache_update(self, addr, sensor_status):
        for property in sensor_status:
            try:
                property_id = property['sensor_setting_property_id']
                key = "%04x.%04x" % (addr, property_id)
                self._sensor_cache[key] = { 'last_update': time.time(), 'property': property }
                #_LOGGER.debug("property_id=0x%04x, key=%s, property=%s" % (property_id, key, property))
            except Exception:
                pass


    async def sensor_descriptor_get(self, address, app_index):
        client = self.elements[0][SensorClient]
        # FixMe: exception
        try:
            result = await client.descriptor_get([address], app_index=app_index, timeout=G_TIMEOUT)
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
                                          timeout=G_TIMEOUT)
                self.sensor_cache_update(addr, result[addr])
                line = self._sensor_cache.setdefault(key, None)
            except Exception:
                _LOGGER.error("failed to get Sensor, addr: %04x, app_index: %d %s" %
                              (addr, app_index, Exception))
                return None

        return line['property']
