"""BT Mesh Client Application"""
from __future__ import annotations


import asyncio
#import time
#from datetime import datetime, timedelta, timezone
from uuid import UUID

from homeassistant.helpers.dispatcher import async_dispatcher_send

from bluetooth_mesh.application import Application, Element, Capabilities
from bluetooth_mesh.messages.config import GATTNamespaceDescriptor
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

from bt_mesh_ctrl import BtMeshModelId, BtMeshOpcode

from .const import (
    DEFAULT_DBUS_APP_PATH,
    G_SEND_INTERVAL,
    G_TIMEOUT,
    G_UNACK_RETRANSMISSIONS,
    G_UNACK_INTERVAL,
    BT_MESH_MSG,
)

from .time_server import TimeServerMixin
#from .entity import BtMeshEntity


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
    _uuid: str
    hass: HomeAssistant

    subs = (
        (GenericOnOffClient, GenericOnOffOpcode.GENERIC_ONOFF_STATUS),
        (GenericBatteryClient, GenericBatteryOpcode.GENERIC_BATTERY_STATUS),
        (SensorClient, SensorOpcode.SENSOR_STATUS),
        (SensorClient, SensorOpcode.SENSOR_DESCRIPTOR_STATUS),
        (LightLightnessClient, LightLightnessOpcode.LIGHT_LIGHTNESS_STATUS),
        (LightCTLClient, LightCTLOpcode.LIGHT_CTL_STATUS),
        (LightCTLClient, LightCTLOpcode.LIGHT_CTL_TEMPERATURE_RANGE_STATUS),
        (LightHSLClient, LightHSLOpcode.LIGHT_HSL_STATUS),
        (LightHSLClient, LightHSLOpcode.LIGHT_HSL_TARGET_STATUS),
    )


    def __init__(self, hass, uuid, path, token=None):
        """Initialize bluetooth_mesh application."""

        self.hass = hass
        self._uuid = uuid
        self._token_ring = SimpleTokenRing(uuid=uuid)
        self.PATH = path
        self.token_ring.token = token

        # FixMe: callback interface to separetly class
        self.pin_cb = None

        self._lock_get = asyncio.Lock()

        super().__init__(self.hass.loop)



    # replace parent class members
    def get_namespace(self):
        return UUID(self._uuid)

    @property
    def token_ring(self) -> SimpleTokenRing:
        return self._token_ring

    def dbus_disconnected(self, owner) -> any:
        pass

    def _register(self):
        super()._register()

        # start Time Server
        self.time_server_init()

        # ...
        for sub in self.subs:
            client = self.elements[0][sub[0]]
            opcode = sub[1]
            client.app_message_callbacks[opcode].add(self._bt_mesh_msg_callback)


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


    # Entity section
    def _bt_mesh_msg_callback(
        self,
        source: int,
        app_index: int,
        destination: Union[int, UUID],
        message: ParsedMeshMessage
    ):
        async_dispatcher_send(
            self.hass,
            BT_MESH_MSG.format(source, message.opcode),
            source,
            app_index,
            destination,
            message
        )


    async def sensor_descriptor_get(self, address, app_index, passive) -> any:
        client = self.elements[0][SensorClient]
        (cache_valid, result) = self.cache.get(address, SensorOpcode.SENSOR_DESCRIPTOR_STATUS)
        if not cache_valid:
            async with self._lock_get:
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

#    async def thermostat_get(self, address, app_index) -> any:
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

#    async def thermostat_range_get(self, address, app_index) -> any:
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
