"""BT Mesh integration."""
from __future__ import annotations


import asyncio
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import config_validation as cv

from .bt_mesh.application import BtMeshApplication
from .mesh_cfgclient_conf import MeshCfgclientConf

from .const import (
    DOMAIN,
    PLATFORMS,
    BT_MESH_CONFIG,
    BT_MESH_APPLICATION,
    BT_MESH_CFGCLIENT_CONF,
    CONF_DBUS_APP_PATH,
    CONF_DBUS_APP_TOKEN,
    CONF_MESH_CFGCLIENT_CONFIG_PATH,
    DEFAULT_DBUS_APP_PATH,
    DEFAULT_MESH_CFGCLIENT_CONFIG_PATH,
)


import logging
_LOGGER = logging.getLogger(__name__)


CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.All(
            vol.Schema(
                {
                    vol.Optional(CONF_DBUS_APP_PATH, default=DEFAULT_DBUS_APP_PATH): cv.string,
                    vol.Optional(CONF_MESH_CFGCLIENT_CONFIG_PATH, default=DEFAULT_MESH_CFGCLIENT_CONFIG_PATH): cv.string,
                }
            )
        )
    },
    extra=vol.ALLOW_EXTRA
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up integration from config."""

    if DOMAIN in hass.data:
        # one instance only
        return False

    logging.basicConfig(level=logging.DEBUG)

    entry_data = hass.data.setdefault(DOMAIN, {})
    entry_data[BT_MESH_CONFIG] = config[DOMAIN]

    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up BT Mesh from a config entry."""

    _LOGGER.debug("async_setup_entry(): config_entry=%s" % config_entry.data)

    entry_data = hass.data[DOMAIN].setdefault(config_entry.entry_id, {})

    mesh_cfgclient_conf = MeshCfgclientConf(
        filename=config_entry.data[CONF_MESH_CFGCLIENT_CONFIG_PATH]
    )
    mesh_cfgclient_conf.load()
    entry_data[BT_MESH_CFGCLIENT_CONF] = mesh_cfgclient_conf

    application = BtMeshApplication(
        path=config_entry.data[CONF_DBUS_APP_PATH],
        token=config_entry.data[CONF_DBUS_APP_TOKEN]
    )

    # Function: process exception
    await application.dbus_connect()
    await application.connect()

    entry_data[BT_MESH_APPLICATION] = application

    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(config_entry, platform)
        )

    # create a task to track changes in the mesh-cfgclient config file
    async def reload_mesh_network_handler(hass):
        """Reload Mesh network configuration task."""
        while True:
            if mesh_cfgclient_conf.is_modified():
                _LOGGER.debug("reload_mesh_network_handler(), config modified")
                devices = mesh_cfgclient_conf.load()
                # TODO: update mesh config

            await asyncio.sleep(5)

    hass.loop.create_task(reload_mesh_network_handler(hass))

    # start BT Mesh Application scheduller
    application.sched_start(hass);

    # start Time Server
    application.time_server_init()

    return True
