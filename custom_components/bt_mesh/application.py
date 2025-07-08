"""BT Mesh Client Application"""
from __future__ import annotations


import asyncio
from construct import Container
#import time
#from datetime import datetime, timedelta, timezone
from uuid import UUID
#from functools import lru_cache
from construct import Container

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

from . import BtMeshModelId, BtMeshOpcode

from ..const import (
    DEFAULT_DBUS_APP_PATH,
    G_SEND_INTERVAL,
    G_TIMEOUT,
    G_UNACK_RETRANSMISSIONS,
    G_UNACK_INTERVAL,
    G_MESH_CACHE_UPDATE_TIMEOUT,
    G_MESH_CACHE_INVALIDATE_TIMEOUT,
)

from .time_server import TimeServerMixin


import logging
_LOGGER = logging.getLogger(__name__)

# FIXME: for debug
import time



class SimpleTokenRing:
    def __init__(self, uuid):
        self.uuid = str(uuid)
        self.data = dict(token=0, acl={}, network={})

    @property
    def token(self):
        return self.data["token"]

    @token.setter
    def token(self, value):
        self.data["token"] = value

    def acl(self, uuid=None, token=None):
        if all((uuid, token)):
            self.data["acl"][uuid] = token
            return

        return self.data["acl"].get(uuid) if uuid else self.data["acl"].items()

    def drop_acl(self, uuid):
        del self.data["acl"][uuid]



class BtMeshCache:
    _cache: dict
    _update_timeout: dict

    def __init__(self):
        self._cache = dict()
        self._update_timeout = dict()

    @staticmethod
    def key(opcode, extra_key=None) -> str:
        return "%x_%s" % (opcode, str(extra_key)) if extra_key is not None else "%x" % (opcode)

    @staticmethod
    def full_key(address, opcode, extra_key=None) -> str:
        return f"{address:x}_{BtMeshCache.key(opcode, extra_key)}"

    def set_update_timeout(self, address, opcode, update_timeout, extra_key=None) -> None:
        key = BtMeshCache.full_key(address, opcode, extra_key)
        self._update_timeout[key] = update_timeout

    def get_update_timeout(self, address, opcode, update_timeout, extra_key=None) -> int:
        key = BtMeshCache.full_key(address, opcode, extra_key)
#        _LOGGER.debug(f"get_update_timeout(): key={key}")
        return max(
            self._update_timeout.get(key, G_MESH_CACHE_UPDATE_TIMEOUT),
            G_MESH_CACHE_UPDATE_TIMEOUT
        )

    def get(self, address, opcode, extra_key=None) -> (bool, any):
        update_timeout = self.get_update_timeout(address, opcode, extra_key)
        invalidate_timeout = G_MESH_CACHE_INVALIDATE_TIMEOUT     \
            if G_MESH_CACHE_INVALIDATE_TIMEOUT >= update_timeout \
                else update_timeout
#        _LOGGER.debug(f"cache_get(): update_timeout={update_timeout}")
        if address in self._cache:
            line_address = self._cache[address]
            key = BtMeshCache.key(opcode, extra_key)
            if line_address is not None and key in line_address:
                line = line_address[key]
                if (line["last_update"] + invalidate_timeout) >= time.time():
                    valid = (line["last_update"] + update_timeout) >= time.time()
#                    _LOGGER.debug("cache_get[%04x]: all Ok" % (address))
                    return (valid, line["data"])
#                else:
#                    _LOGGER.debug("cache_get[%04x]: line not found or expired" % (address))
#            else:
#                _LOGGER.debug("cache_get[%04x]: line_address is none (%s) or key %s not found (%s)" % (address, str(line_address is not None), key, str(key in line_address)))
#        else:
#            _LOGGER.debug("cache_get[%04x]: address not found" % (address))

        return (False, None)

    def update(self, address, opcode, data, extra_key=None):
        if not address in self._cache:
            self._cache[address] = dict()
        key = BtMeshCache.key(opcode, extra_key)
        self._cache[address][key] = {
            "last_update": time.time(),
            "opcode": opcode,
            "data": data
        }
#        _LOGGER.debug("cache_update[%04x]: key=%s, %s" % (address, key, repr(data)))

    def invalidate(self, address, opcode, extra_key=None):
        if opcode is None:
            if address in  self._cache:
                for key, line in self._cache[address].items():
                    update_timeout = self.get_update_timeout(address, line["opcode"], extra_key)
#                    _LOGGER.debug(f"cache_invalidate(): update_timeout={update_timeout}")
                    line["last_update"] =  time.time() - update_timeout
#                    _LOGGER.debug("cache_invalidate2[%04x]: key=%s" % (address, key))
        else:
            key = BtMeshCache.key(opcode, extra_key)
            update_timeout = self.get_update_timeout(address, opcode, extra_key)
#            _LOGGER.debug(f"cache_invalidate(): update_timeout={update_timeout}")
            if address in self._cache and key in self._cache[address]:
                line = self._cache[address][key]
                line["last_update"] =  time.time() - update_timeout
#                _LOGGER.debug("cache_invalidate2[%04x]: key=%s" % (address, key))

    def update_and_invalidate(self, address, opcode, data, extra_key=None):
        if not address in self._cache:
            self._cache[address] = dict()

        for key, line in self._cache[address].items():
            update_timeout = self.get_update_timeout(address, line["opcode"], extra_key)
#            _LOGGER.debug(f"cache_update_and_invalidate(): update_timeout={update_timeout}")
            line["last_update"] = time.time() - G_MESH_CACHE_UPDATE_TIMEOUT
#            _LOGGER.debug("cache_update_and_invalidate[%04x]: key=%s" % (address, key))

        key = BtMeshCache.key(opcode, extra_key)
        update_timeout = self.get_update_timeout(address, opcode, extra_key)
#        _LOGGER.debug(f"cache_update_and_invalidate(): update_timeout={update_timeout}")
        self._cache[address][key] = {
            "last_update": time.time() - update_timeout,
            "opcode": opcode,
            "data": data
        }
#        _LOGGER.debug("cache_update_and_invalidate[%04x]: key=%s, %s" % (address, key, repr(data)))

    def receive_message(
        self,
        _source: int,
        _app_index: int,
        _destination: Union[int, UUID],
        message: ParsedMeshMessage,
    ):
        #if message.opcode == GenericOnOffOpcode.GENERIC_ONOFF_STATUS:
        #    _LOGGER.debug("CACHE_RECEIVE_STATUS receive %04x->%04x [%f]" % (_source, _destination, time.time()))
#        _LOGGER.debug("CACHE_RECEIVE_STATUS receive %04x->%04x opcode: %x [%f]" % (_source, _destination, message.opcode, time.time()))
        opcode_name = BtMeshOpcode.get(message.opcode).name.lower()
        self.update(
            _source,
            message.opcode,
            message[opcode_name]
        )
        if _source == 0x010a:
            _LOGGER.debug("CACHE_RECEIVE_STATUS receive %04x->%04x %s" % (_source, _destination, message[opcode_name]))



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


class BtMeshApplication(Application, TimeServerMixin):
    COMPANY_ID = 0x05f1  # Linux Foundation
    PRODUCT_ID = 0x4148  # HA - HomeAssistant
    VERSION_ID = 1
    ELEMENTS = {
        0: MainElement,
    }
    CAPABILITIES = [Capabilities.OUT_NUMERIC]

    CRPL = 32768
    PATH = DEFAULT_DBUS_APP_PATH

    _token_ring: SimpleTokenRing
    hass: HomeAssistant
    cache: BtMeshCache


    def __init__(self, hass, uuid, path, token=None):
        """Initialize bluetooth_mesh application."""

        self.hass = hass
        self._token_ring = SimpleTokenRing(uuid=uuid)
        self.PATH = path
        self.token_ring.token = token

        # FixMe: callback interface to separetly class
        self.pin_cb = None

        self.cache = BtMeshCache()

        self._lock_get = asyncio.Lock()

        super().__init__(self.hass.loop)


    # replace parent class members
    def get_namespace(self):
        _LOGGER.debug("UUID: %s" % (UUID(self._uuid)))
        return UUID(self._uuid)

    @property
    def token_ring(self) -> SimpleTokenRing:
        return self._token_ring

    def dbus_disconnected(self, owner) -> Any:
        pass

    def _register(self):
        super()._register()

        # start Time Server
        self.time_server_init()

        # cache will automatically take values from the Network
        self.generic_onoff_init_receive_status()
        self.sensor_init_receive_status()
        self.generic_battery_init_receive_status()
        self.light_lightness_init_receive_status()
        self.light_ctl_init_receive_status()
        self.light_hsl_init_receive_status()


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
    def generic_onoff_init_receive_status(self) -> None:
        client = self.elements[0][GenericOnOffClient]
        client.app_message_callbacks[GenericOnOffOpcode.GENERIC_ONOFF_STATUS].add(self.cache.receive_message)

    async def generic_onoff_get(self, address, app_index) -> Container | None:
        """Get GenericOnOff state"""
        client = self.elements[0][GenericOnOffClient]
        (cache_valid, result) = self.cache.get(address, GenericOnOffOpcode.GENERIC_ONOFF_STATUS)
        if not cache_valid:
            try:
                result = await client.get(
                    address,
                    app_index=app_index,
                    send_interval=G_SEND_INTERVAL,
                    timeout=G_TIMEOUT,
                )
            except asyncio.TimeoutError:
                pass
        #_LOGGER.debug("Get GenericOnOff state %04x: result %s [%f]" % (address, repr(result), time.time()))
        return result

    async def generic_onoff_set(self, address, app_index, state, transition_time=None) -> None:
        """Set GenericOnOff state"""
        try:
            client = self.elements[0][GenericOnOffClient]
            await client.set(
                address,
                app_index=app_index,
                onoff=state,
                delay=None if transition_time is None else 0,
                transition_time=transition_time,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT,
            )
            self.cache.update_and_invalidate(
                address,
                GenericOnOffOpcode.GENERIC_ONOFF_STATUS,
                Container(present_onoff=1 if state else 0)
            )
        except asyncio.TimeoutError:
            pass
        #_LOGGER.debug("Set GenericOnOff state %04x: result %s [%f]" % (address, repr(state), time.time()))

    # LightLightness
    def light_lightness_init_receive_status(self) -> None:
        client = self.elements[0][LightLightnessClient]
        client.app_message_callbacks[LightLightnessOpcode.LIGHT_LIGHTNESS_STATUS].add(self.cache.receive_message)

    async def light_lightness_get(self, address, app_index) -> Container | None:
        """Get LightLightness state"""
        client = self.elements[0][LightLightnessClient]
        (cache_valid, result) = self.cache.get(address, LightLightnessOpcode.LIGHT_LIGHTNESS_STATUS)
        if not cache_valid:
            try:
                result = await client.get(
                    address,
                    app_index=app_index,
                    send_interval=G_SEND_INTERVAL,
                    timeout=G_TIMEOUT,
                )
            except asyncio.TimeoutError:
                pass
#        _LOGGER.debug("Get LightLightness state %04x: result %s [%f]" % (address, repr(result), time.time()))
        return result

    async def light_lightness_set(self, address, app_index, lightness, transition_time=None) -> None:
        """Set LightLightness lightness"""
        client = self.elements[0][LightLightnessClient]
        try:
            await client.set(
                address,
                app_index=app_index,
                lightness=lightness,
                delay=None if transition_time is None else 0,
                transition_time=transition_time,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT,
            )
            self.cache.update_and_invalidate(
                address,
                LightLightnessOpcode.LIGHT_LIGHTNESS_STATUS,
                Container(present_lightness=lightness)
            )
        except asyncio.TimeoutError:
            pass


    # LightCTL
    def light_ctl_init_receive_status(self):
        client = self.elements[0][LightCTLClient]
        client.app_message_callbacks[LightCTLOpcode.LIGHT_CTL_STATUS].add(self.cache.receive_message)
        client.app_message_callbacks[LightCTLOpcode.LIGHT_CTL_TEMPERATURE_RANGE_STATUS].add(self.cache.receive_message)

    async def light_ctl_get(self, address, app_index) -> Container | None:
        """Get LightCTL state"""
        client = self.elements[0][LightCTLClient]
        (cache_valid, result) = self.cache.get(address, LightCTLOpcode.LIGHT_CTL_STATUS)
        if not cache_valid:
            try:
                result = await client.get(
                    address,
                    app_index=app_index,
                    send_interval=G_SEND_INTERVAL,
                    timeout=G_TIMEOUT,
                )
            except asyncio.TimeoutError:
                pass
        #_LOGGER.debug("Get LightCTL state %04x: result %s [%f]" % (address, repr(result), time.time()))
        return result

    async def light_ctl_temperature_range_get(self, address, app_index) -> Container | None:
        """Get LightCTL temperature range"""
        client = self.elements[0][LightCTLClient]
        (cache_valid, result) = self.cache.get(address, LightCTLOpcode.LIGHT_CTL_TEMPERATURE_RANGE_STATUS)
        if not cache_valid:
            try:
                result = await client.temperature_range_get(
                    address,
                    app_index=app_index,
                    send_interval=G_SEND_INTERVAL,
                    timeout=G_TIMEOUT,
                )
            except asyncio.TimeoutError:
                pass
        #_LOGGER.debug("Get LightCTL Temperature Range state %04x: result %s [%f]" % (address, repr(result), time.time()))
        return result

    async def light_ctl_set(self, address, app_index, lightness, temperature, transition_time=None) -> None:
        """Set LightCTL state"""
        client = self.elements[0][LightCTLClient]
        try:
            await client.set(
                address,
                app_index=app_index,
                ctl_lightness=lightness,
                ctl_temperature=temperature,
                ctl_delta_uv=0,
                delay=None if transition_time is None else 0,
                transition_time=transition_time,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT
            )
            self.cache.update_and_invalidate(
                address,
                LightCTLOpcode.LIGHT_CTL_STATUS,
                Container(
                    present_ctl_lightness=lightness,
                    present_ctl_temperature=temperature
                )
            )
        except asyncio.TimeoutError:
            pass
        #_LOGGER.debug("Set LightCTL state %04x: lightness %d, temperature %d" % (address, lightness, temperature))


    # LightHSL
    def light_hsl_init_receive_status(self) -> None:
        client = self.elements[0][LightHSLClient]
        client.app_message_callbacks[LightHSLOpcode.LIGHT_HSL_STATUS].add(self.cache.receive_message)
        client.app_message_callbacks[LightHSLOpcode.LIGHT_HSL_TARGET_STATUS].add(self.cache.receive_message)

    async def light_hsl_get(self, address, app_index) -> Container | None:
        """Get LightHSL state"""
        client = self.elements[0][LightHSLClient]
        (cache_valid, result) = self.cache.get(address, LightHSLOpcode.LIGHT_HSL_STATUS)
        if not cache_valid:
            try:
                result = await client.get(
                    address,
                    app_index=app_index,
                    send_interval=G_SEND_INTERVAL,
                    timeout=G_TIMEOUT,
                )
            except asyncio.TimeoutError:
                pass
#        _LOGGER.debug("Get LightHSL state %04x: result %s [%f]" % (address, repr(result), time.time()))
        return result

    async def light_hsl_get_target(self, address, app_index) -> Container | None:
        """Get LightHSL state"""
        client = self.elements[0][LightHSLClient]
        (cache_valid, result) = self.cache.get(address, LightHSLOpcode.LIGHT_HSL_TARGET_STATUS)
        if not cache_valid:
            try:
                result = await client.target_get(
                    address,
                    app_index=app_index,
                    send_interval=G_SEND_INTERVAL,
                    timeout=G_TIMEOUT,
                )
            except asyncio.TimeoutError:
                pass
#        _LOGGER.debug("Get LightHSL target state %04x: result %s [%f]" % (address, repr(result), time.time()))
        return result

    async def light_hsl_set(self, address, app_index, lightness, hue, saturation, transition_time=None) -> None:
        """Set LightHSL lightness, hue and saturation"""
        client = self.elements[0][LightHSLClient]
        try:
            await client.set(
                address,
                app_index=app_index,
                hsl_lightness=lightness,
                hsl_hue=hue,
                hsl_saturation=saturation,
                delay=None if transition_time is None else 0,
                transition_time=transition_time,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT
            )
            self.cache.update_and_invalidate(
                address,
                LightHSLOpcode.LIGHT_HSL_STATUS,
                Container(
                    hsl_lightness=lightness,
                    hsl_hue=hue,
                    hsl_saturation=saturation
                )
            )
            self.cache.update_and_invalidate(
                address,
                LightHSLOpcode.LIGHT_HSL_TARGET_STATUS,
                Container(
                    hsl_lightness=lightness,
                    hsl_hue=hue,
                    hsl_saturation=saturation
                )
            )
        except asyncio.TimeoutError:
            pass


    # Sensor
    def sensor_init_receive_status(self) -> None:
        def receive_sensor_status(
            _source: int,
            _app_index: int,
            _destination: Union[int, UUID],
            message: ParsedMeshMessage,
        ):
            opcode_name = BtMeshOpcode.get(message.opcode).name.lower()
            result = message[opcode_name]
            for property in result:
                self.cache.update(
                    _source,
                    message.opcode,
                    property,
                    extra_key=property.sensor_setting_property_id
                )

            if _source == 0x010a:
                _LOGGER.debug("CACHE_RECEIVE_STATUS receive %04x->%04x %s" % (_source, _destination, message[opcode_name]))

        client = self.elements[0][SensorClient]
        client.app_message_callbacks[SensorOpcode.SENSOR_DESCRIPTOR_STATUS].add(self.cache.receive_message)
        client.app_message_callbacks[SensorOpcode.SENSOR_STATUS].add(receive_sensor_status)


    async def sensor_descriptor_get(self, address, app_index, passive) -> Container | None:
        client = self.elements[0][SensorClient]
        (cache_valid, result) = self.cache.get(address, SensorOpcode.SENSOR_DESCRIPTOR_STATUS)
        if not cache_valid:
            try:
                result = await client.descriptor_get(
                    address,
                    app_index=app_index,
                    send_interval=G_SEND_INTERVAL,
                    timeout=G_TIMEOUT)
            except asyncio.TimeoutError:
                pass
        #_LOGGER.debug("sensor_descriptor_get() result = %s" % (repr(result)))
        return result


    async def sensor_get(self, address, app_index, property_id, passive) -> Container | None:
        client = self.elements[0][SensorClient]
        (cache_valid, property) = self.cache.get(
            address,
            SensorOpcode.SENSOR_STATUS,
            extra_key=property_id
        )
        if not cache_valid and not passive:
            try:
                result = await client.get(
                    address,
                    app_index=app_index,
                    send_interval=G_SEND_INTERVAL,
                    timeout=G_TIMEOUT,
                )
                if result:
                    for property in result:
                        if property_id == property.sensor_setting_property_id:
                            return property
                    return None
            except asyncio.TimeoutError:
                pass

        return property


    # Generic Battery
    def generic_battery_init_receive_status(self) -> None:
        client = self.elements[0][GenericBatteryClient]
        client.app_message_callbacks[GenericBatteryOpcode.GENERIC_BATTERY_STATUS].add(self.cache.receive_message)


    async def generic_battery_get(self, address, app_index) -> Container | None:
        """Get GenericBattery state"""
        client = self.elements[0][GenericBatteryClient]
        (cache_valid, result) = self.cache.get(address, GenericBatteryOpcode.GENERIC_BATTERY_STATUS)
        if not cache_valid:
            try:
                result = await client.get(
                    address,
                    app_index=app_index,
                    send_interval=G_SEND_INTERVAL,
                    timeout=G_TIMEOUT)
            except asyncio.TimeoutError:
                pass
        return result


    # Vendor Thermostat
#    def thermostat_init_receive_status(self) -> None:
#        def receive_status(
#            _source: int,
#            _app_index: int,
#            _destination: Union[int, UUID],
#            message: ParsedMeshMessage,
#        ):
#            vendor_message = message['vendor_thermostat']
#            if vendor_message.subopcode == ThermostatSubOpcode.THERMOSTAT_STATUS:
#                if vendor_message.thermostat_status.status_code == ThermostatStatusCode.GOOD:
#                    self.cache_update(
#                        _source,
#                        BtMeshModelId.ThermostatServer,
#                        vendor_message.thermostat_status,
#                        extra_key=ThermostatSubOpcode.THERMOSTAT_STATUS
#                )
#            elif vendor_message.subopcode == ThermostatSubOpcode.THERMOSTAT_RANGE_STATUS:
#                self.cache_update(
#                    _source,
#                    BtMeshModelId.ThermostatServer,
#                    vendor_message.thermostat_range_status,
#                    extra_key=ThermostatSubOpcode.THERMOSTAT_RANGE_STATUS
#                )

#        client = self.elements[0][ThermostatClient]
#        client.app_message_callbacks[ThermostatOpcode.VENDOR_THERMOSTAT].add(receive_status)

#    async def thermostat_get(self, address, app_index) -> Container | None:
#        """Get Vendor Thermostat state"""
#        client = self.elements[0][ThermostatClient]
#        return await self.cache_proxy(
#            address,
#            BtMeshModelId.ThermostatServer,
#            client.get(
#                [address],
#                app_index=app_index,
#                send_interval=G_SEND_INTERVAL,
#                timeout=G_TIMEOUT,
#            ),
#            extra_key=ThermostatSubOpcode.THERMOSTAT_STATUS
#        )

#    async def thermostat_range_get(self, address, app_index) -> Container | None:
#        """Get Vendor Thermostat range"""
#        client = self.elements[0][ThermostatClient]
#        return await self.cache_proxy(
#            address,
#            BtMeshModelId.ThermostatServer,
#            client.range_get(
#                [address],
#                app_index=app_index,
#                send_interval=G_SEND_INTERVAL,
#                timeout=G_TIMEOUT,
#            ),
#            extra_key=ThermostatSubOpcode.THERMOSTAT_RANGE_STATUS
#        )

#    async def thermostat_set(self, address, app_index, onoff, temperature) -> None:
#        """Get Vendor Thermostat state"""
#        client = self.elements[0][ThermostatClient]
#
#        async with self._lock:
#            await client.set(
#                [address],
#                app_index=app_index,
#                onoff=onoff,
#                mode=ThermostatMode.MANUAL,
#                temperature=temperature,
#                send_interval=G_SEND_INTERVAL,
#                timeout=G_TIMEOUT,
#            )
#            self.cache_invalidate(
#                address,
#                BtMeshModelId.ThermostatServer,
#                extra_key=ThermostatSubOpcode.THERMOSTAT_STATUS
#            )
