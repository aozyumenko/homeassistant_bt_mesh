"""BT Mesh Client Application"""
from __future__ import annotations

import asyncio
from uuid import UUID

#from dataclasses import asdict, dataclass, field
from dataclasses import dataclass

from homeassistant.helpers.dispatcher import async_dispatcher_send

from bluetooth_mesh.application import Application, Element, Capabilities
from bluetooth_mesh.messages.config import GATTNamespaceDescriptor
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
    ThermostatStatusCode,
)
from bluetooth_mesh.messages.properties import PropertyID

from bt_mesh_ctrl import BtMeshModelId, BtMeshOpcode

from .time_server import TimeServerMixin
from .const import (
    DEFAULT_DBUS_APP_PATH,
    G_SEND_INTERVAL,
    G_TIMEOUT,
    G_UNACK_RETRANSMISSIONS,
    G_UNACK_INTERVAL,
    BT_MESH_MSG,
)


import logging
_LOGGER = logging.getLogger(__name__)

# FIXME: for debug
import time




@dataclass
class BtMeshData:
    app: BtMeshApplication



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
        (ThermostatClient, ThermostatOpcode.VENDOR_THERMOSTAT),
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
        """Passing messages to Bt mesh entities."""
        async_dispatcher_send(
            self.hass,
            BT_MESH_MSG.format(source, message.opcode),
            source,
            app_index,
            destination,
            message
        )

    def bluetooth_mesh_get(query_func):
        """Decorator for getting the state of a Bt mesh model with a global lock,
           preventing a large number of simultaneous requests."""
        async def wrapper(*args, **kwargs):
            self = args[0]
            async with self._lock_get:
                try:
                    return await query_func(*args, **kwargs)
                except asyncio.TimeoutError:
                    pass
            return None
        return wrapper

    def bluetooth_mesh_set(query_func):
        """Decorator for setting the state of a Bt grid model
           with handling of the Timeout exception."""
        async def wrapper(*args, **kwargs):
            self = args[0]
            try:
                return await query_func(*args, **kwargs)
            except asyncio.TimeoutError:
                pass
            return None
        return wrapper


    # GenericOnOff client
    @bluetooth_mesh_get
    async def generic_onoff_get(self, destination: int, app_index: int) -> any:
        client = self.elements[0][GenericOnOffClient]
        return await client.get(
            destination=destination,
            app_index=app_index,
            send_interval=G_SEND_INTERVAL,
            timeout=G_TIMEOUT
        )

    @bluetooth_mesh_set
    async def generic_onoff_set(
        self,
        destination: int,
        app_index: int,
        onoff: int,
        transition_time: float=None
    ) -> any:
        """Set GenericOnOff state"""
        client = self.elements[0][GenericOnOffClient]
        return await client.set(
            destination=destination,
            app_index=app_index,
            onoff=onoff,
            delay=None if transition_time is None else 0,
            transition_time=transition_time,
            send_interval=G_SEND_INTERVAL,
            timeout=G_TIMEOUT
        )

    # LightLightness
    @bluetooth_mesh_get
    async def light_lightness_get(self, destination: int, app_index: int) -> any:
        """Get LightLightness state"""
        client = self.elements[0][LightLightnessClient]
        return await client.get(
            destination=destination,
            app_index=app_index,
            send_interval=G_SEND_INTERVAL,
            timeout=G_TIMEOUT
        )

    @bluetooth_mesh_set
    async def light_lightness_set(
        self,
        destination: int,
        app_index: int,
        lightness: int,
        transition_time: float=None
    ) -> any:
        """Set LightLightness lightness"""
        client = self.elements[0][LightLightnessClient]
        return await client.set(
            destination=destination,
            app_index=app_index,
            lightness=lightness,
            delay=None if transition_time is None else 0,
            transition_time=transition_time,
            send_interval=G_SEND_INTERVAL,
            timeout=G_TIMEOUT
        )

    # LightCTL
    @bluetooth_mesh_get
    async def light_ctl_get(self, destination: int, app_index: int) -> any:
        """Get LightCTL state"""
        client = self.elements[0][LightCTLClient]
        return await client.get(
            destination=destination,
            app_index=app_index,
            send_interval=G_SEND_INTERVAL,
            timeout=G_TIMEOUT
        )

    @bluetooth_mesh_get
    async def light_ctl_temperature_range_get(self, destination: int, app_index: int) -> any:
        """Get LightCTL temperature range"""
        client = self.elements[0][LightCTLClient]
        return await client.temperature_range_get(
            destination=destination,
            app_index=app_index,
            send_interval=G_SEND_INTERVAL,
            timeout=G_TIMEOUT
        )

    @bluetooth_mesh_set
    async def light_ctl_set(
        self,
        destination: int,
        app_index: int,
        ctl_lightness: int,
        ctl_temperature: int,
        transition_time: float=None
    ) -> any:
        """Set LightCTL state"""
        try:
            client = self.elements[0][LightCTLClient]
            return await client.set(
                destination=destination,
                app_index=app_index,
                ctl_lightness=ctl_lightness,
                ctl_temperature=ctl_temperature,
                ctl_delta_uv=0,
                delay=None if transition_time is None else 0,
                transition_time=transition_time,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT
            )
        except asyncio.TimeoutError:
            pass
        return None

    # LightHSL
    @bluetooth_mesh_get
    async def light_hsl_get(self, destination: int, app_index: int) -> any:
        """Get LightHSL state"""
        client = self.elements[0][LightHSLClient]
        return await client.get(
            destination=destination,
            app_index=app_index,
            send_interval=G_SEND_INTERVAL,
            timeout=G_TIMEOUT
        )

    @bluetooth_mesh_get
    async def light_hsl_get_target(self, destination: int, app_index: int) -> any:
        """Get LightHSL state"""
        client = self.elements[0][LightHSLClient]
        return await client.target_get(
            destination=destination,
            app_index=app_index,
            send_interval=G_SEND_INTERVAL,
            timeout=G_TIMEOUT
        )

    @bluetooth_mesh_set
    async def light_hsl_set(
        self,
        destination: int,
        app_index: int,
        hsl_lightness: int,
        hsl_hue: int,
        hsl_saturation: int,
        transition_time: float=None
    ) -> any:
        """Set LightHSL lightness, hue and saturation"""
        client = self.elements[0][LightHSLClient]
        return await client.set(
            destination=destination,
            app_index=app_index,
            hsl_lightness=hsl_lightness,
            hsl_hue=hsl_hue,
            hsl_saturation=hsl_saturation,
            delay=None if transition_time is None else 0,
            transition_time=transition_time,
            send_interval=G_SEND_INTERVAL,
            timeout=G_TIMEOUT
        )

    # GenericBattery
    @bluetooth_mesh_get
    async def generic_battery_get(self, destination: int, app_index: int) -> any:
        """Get GenericBattery state"""
        client = self.elements[0][GenericBatteryClient]
        return await client.get(
            destination=destination,
            app_index=app_index,
            send_interval=G_SEND_INTERVAL,
            timeout=G_TIMEOUT
        )

    # Sensor
    @bluetooth_mesh_get
    async def sensor_descriptor_get(self, destination: int, app_index: int) -> any:
        client = self.elements[0][SensorClient]
        return await client.descriptor_get(
            destination=destination,
            app_index=app_index,
            send_interval=G_SEND_INTERVAL,
            timeout=G_TIMEOUT
        )

    @bluetooth_mesh_get
    async def sensor_get(
        self,
        destination: int,
        app_index: int,
        property_id: PropertyID
    ) -> any:
        client = self.elements[0][SensorClient]
        result = await client.get(
            destination=destination,
            app_index=app_index,
            send_interval=G_SEND_INTERVAL,
            timeout=G_TIMEOUT
        )
        if result:
            for property in result:
                if property_id == property.sensor_setting_property_id:
                    return property
        return None


    # Vendor Thermostat
    @bluetooth_mesh_get
    async def thermostat_get(self, destination: int, app_index: int) -> any:
        """Get Vendor Thermostat state."""
        client = self.elements[0][ThermostatClient]
        return await client.get(
            destination=destination,
            app_index=app_index,
            send_interval=G_SEND_INTERVAL,
            timeout=G_TIMEOUT
        )

    @bluetooth_mesh_get
    async def thermostat_range_get(self, destination: int, app_index: int) -> any:
        """Get Vendor Thermostat themperature range."""
        client = self.elements[0][ThermostatClient]
        return await client.range_get(
            destination=destination,
            app_index=app_index,
            send_interval=G_SEND_INTERVAL,
            timeout=G_TIMEOUT
        )

    @bluetooth_mesh_set
    async def thermostat_set(
        self,
        destination: int,
        app_index: int,
        onoff: int,
        temperature: float
    ) -> any:
        """Set Vendor Thermostat state."""
        client = self.elements[0][ThermostatClient]
        return await client.set(
            destination=destination,
            app_index=app_index,
            onoff=onoff,
            mode=ThermostatMode.MANUAL,
            temperature=temperature,
            send_interval=G_SEND_INTERVAL,
            timeout=G_TIMEOUT
        )
