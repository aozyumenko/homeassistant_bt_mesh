"""..."""
from __future__ import annotations


import sys
sys.path.append('/home/scg/src/bluez/aozyumenko-python-bluetooth-mesh')


import asyncio
import logging
from enum import IntEnum

from bluetooth_mesh.application import Application, Element, Capabilities
from bluetooth_mesh.models import (
    HealthClient,
)
from bluetooth_mesh.models.generic.onoff import GenericOnOffClient
#from bluetooth_mesh.models.generic.level import GenericLevelClient
from bluetooth_mesh.models.generic.dtt import GenericDTTClient
from bluetooth_mesh.models.generic.ponoff import GenericPowerOnOffClient
from bluetooth_mesh.models.scene import SceneClient
#from bluetooth_mesh.models.light.lightness import LightLightnessClient
#from bluetooth_mesh.models.light.ctl import LightCTLClient
#from bluetooth_mesh.models.light.hsl import LightHSLClient
from bluetooth_mesh.messages.config import GATTNamespaceDescriptor

from .const import DBUS_APP_PATH



_LOGGER = logging.getLogger(__name__)



# FixMe: add comment
class BtMeshModelId(IntEnum):
    GenericOnOffServer = 0x1000
    GenericPowerOnOffServer = 0x1006
    GenericPowerOnOffSetupServer = 0x1007
    LightLightnessServer = 0x1300
    LightLightnessSetupServer = 0x1301
    LightCTLServer = 0x1303
    LightCTLSetupServer = 0x1304
    LightCTLTemperatureServer = 0x1306
    LightHSLServer = 0x1307
    LightHSLSetupServer = 0x1308
    LightHSLHueServer = 0x130a
    LightHSLSaturationServer = 0x130b

    @classmethod
    def has_value(_class, val: int):
        return val in _class._value2member_map_

    @classmethod
    def get_name(_class, val: int):
        return BtMeshModelId(val).name if BtMeshModelId.has_value(val) else "%04x" % (val)



class MainElement(Element):
    LOCATION = GATTNamespaceDescriptor.MAIN
    MODELS = [
        HealthClient,
        SceneClient,
        GenericOnOffClient,
        GenericDTTClient,
        GenericPowerOnOffClient,
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


    def __init__(self, token=None):
        """Initialize bluetooth_mesh application."""
        loop = asyncio.get_event_loop()
        super().__init__(loop)

        self.TOKEN = token
        # FixMe: callback interface to separetly class
        self.pin_cb = None

        self._event_loop = None



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

    # Switch

    async def mesh_generic_onoff_get(self, address, app_index):
        """Get GenericOnOff state"""
        client = self.elements[0][GenericOnOffClient]
        # FixMe: exception
        try:
            result = await client.get([address], app_index=app_index, timeout=5)
            # FixMe: check result
            #_LOGGER.error("mesh_generic_onoff_get(): address=0x%x, present_onoff=%d" % (address, result[address].present_onoff))
            return result[address].present_onoff != 0
        except Exception:
            _LOGGER.error("mesh_generic_onoff_get(): address=%04x, app_index=%d, %s" % (address, app_index, Exception))

        return False

    async def mesh_generic_onoff_set(self, address, app_index, state):
        """Set GenericOnOff"""
        client = self.elements[0][GenericOnOffClient]
        #_LOGGER.debug("mesh_generic_onoff_set(): started")
        await client.set([address], app_index=app_index, onoff=state, send_interval=0.5, timeout=60, delay=0)
        #_LOGGER.debug("mesh_generic_onoff_set(): finished")
