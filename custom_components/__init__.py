"""Bluetooth Mesh Client integration."""
from __future__ import annotations

import asyncio
import logging

#from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
#from homeassistant.const import (
#    CONF_DEVICES,
#    CONF_DISCOVERY,
#    CONF_MAC,
#    CONF_NAME,
#    CONF_TEMPERATURE_UNIT,
#    CONF_UNIQUE_ID,
#    EVENT_HOMEASSISTANT_STOP,
#)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import config_validation as cv
#from homeassistant.helpers.entity_registry import (
#    async_entries_for_device,
#)
#from homeassistant.util import dt
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.const import CONF_DEVICES, CONF_NAME, CONF_ADDRESS, CONF_MODEL

# FIXME: !!!!!!!!!!!!!!!
from homeassistant.helpers.service import async_register_admin_service

import voluptuous as vol


from .const import (
    DOMAIN,
    PLATFORMS,
    MESH_CFGCLIENT_CONFIG_PATH,
    BT_MESH_CONFIG,
    BT_MESH_APPLICATION,
    BT_MESH_CFGCLIENT_CONF,
    CONF_APP_KEY,
    CONF_SENSOR_PROPERTY_ID,
)
from .bt_mesh import BtMeshApplication, BtMeshModelId
from .mesh_cfgclient_conf import MeshCfgclientConf


_LOGGER = logging.getLogger(__name__)

u16_int = vol.All(vol.Coerce(int), vol.Range(min=0x0000, max=0xffff))


# TODO: drop device configuration
DEVICE_SCHEMA = {
    vol.Optional(CONF_NAME): cv.string,
    vol.Optional(CONF_ADDRESS): u16_int,
    vol.Optional(CONF_MODEL): u16_int,
    vol.Optional(CONF_APP_KEY): cv.positive_int,
#    vol.Optional(CONF_SENSOR_PROPERTY_ID): u16_int,
}


CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.All(
            vol.Schema(
                {
                    vol.Optional(CONF_DEVICES, default=[]): vol.All(
                        cv.ensure_list, [DEVICE_SCHEMA]
                    ),
                }
            )
        )
    },
    extra=vol.ALLOW_EXTRA, # FixMe:???
)



@asyncio.coroutine
def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up integration from config."""

    if DOMAIN in hass.data:
        # one instance only
        return False

    logging.basicConfig(level=logging.DEBUG)

    _LOGGER.debug("async_setup(): config=%s" % config)


    entry_data = hass.data.setdefault(DOMAIN, {})
    entry_data[BT_MESH_CONFIG] = config       # TODO config[DOMAIN]
    entry_data[BT_MESH_CFGCLIENT_CONF] = MeshCfgclientConf(
        filename=MESH_CFGCLIENT_CONFIG_PATH
    )

    async def reload_mesh_network_handler(hass):
        """Reload Mesh network configuration task."""
        while True:
            conf = hass.data.get(DOMAIN)
            mesh_cgfclient_conf = conf[BT_MESH_CFGCLIENT_CONF]
            if mesh_cgfclient_conf.is_modified():
                _LOGGER.debug("reload_mesh_network_handler(), config modified")
                devices = mesh_cgfclient_conf.load()
                # TODO: update mesh config

            await asyncio.sleep(5)

    hass.loop.create_task(reload_mesh_network_handler(hass))

    return True



async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up OctoPrint from a config entry."""

    _LOGGER.debug("async_setup_entry(): config_entry=%s" % config_entry.data)

    entry_data = hass.data[DOMAIN].setdefault(config_entry.entry_id, {})

    application = BtMeshApplication(
        token=config_entry.data["token"]
    )
    # Function: process exception
    await application.dbus_connect()
    await application.connect()

    entry_data[BT_MESH_APPLICATION] = application

    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(config_entry, platform)
        )

    return True



class BtMeshEntity(Entity):
    """Representation of a BT Mesh service."""

    _application: BtMeshApplication

    def __init__(self, application, uuid, cid, pid, vid, addr, model_id, app_index):
        """Initialize the device."""
        self._application = application
        self._unicast_addr = addr
        self._model_id = model_id
        self._app_index = app_index

        self.uuid: str = uuid
        self.cid: int = cid
        self.pid: int = pid
        self.vid: int = vid
        self.product: str = "0x%04x" % (self.pid)
        self.company: str = "0x%04x" % (self.cid)

        self._attr_name = "%04x-%s" % (self._unicast_addr, BtMeshModelId.get_name(model_id))
        self._attr_unique_id = "%04x-%04x" % (self._unicast_addr, self._model_id)

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.uuid)},
            name=self.uuid,
            model=self.product,
            manufacturer=self.company,
            sw_version=("0x%04x") % self.vid,
        )

    @property
    def unicast_addr(self):
        """Return the unicast address of the node."""
        return self._unicast_addr

    @property
    def model_id(self):
        """Return the Model Id."""
        return self._model_id

    @property
    def app_index(self):
        """Return the application key index of the model."""
        return self._app_index

    @property
    def application(self):
        """Return the BT Mesh Client application."""
        return self._application
