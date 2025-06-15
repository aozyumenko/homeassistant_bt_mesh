"""BT Mesh integration."""
from __future__ import annotations


import asyncio
import voluptuous as vol

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import config_validation as cv, device_registry as dr, entity_registry as er
#from homeassistant.helpers import async_entries_for_label

from homeassistant.helpers.dispatcher import async_dispatcher_send


from .bt_mesh.application import BtMeshApplication
from .bt_mesh.mesh_cfgclient_conf import MeshCfgclientConf
from .bt_mesh import BtMeshModelId

# FIXME: for testing only
from .bt_mesh.entity import BtMeshEntity


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
    BT_MESH_DISCOVERY_ENTITY_NEW,
)


import logging
_LOGGER = logging.getLogger(__name__)

# FIXME: for debug
import json

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

    hass.data[DOMAIN] = {
        BT_MESH_CONFIG: config[DOMAIN],
    }

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BT Mesh from a config entry."""

    _LOGGER.debug("async_setup_entry(): entry_id=%s, entry_domain=%s, entry=%s" % (entry.entry_id, entry.domain, entry.data))

    entry_data = hass.data[DOMAIN].setdefault(entry.entry_id, {})
    _LOGGER.debug("entry_data=%s" % (repr(entry)))

    # load mesh network config
    mesh_cfgclient_conf = MeshCfgclientConf(
        filename=entry.data[CONF_MESH_CFGCLIENT_CONFIG_PATH]
    )
    await hass.async_add_executor_job(mesh_cfgclient_conf.load)
    entry_data[BT_MESH_CFGCLIENT_CONF] = mesh_cfgclient_conf

    # create BtMesh application
    application = BtMeshApplication(
        hass,
        uuid = entry.entry_id,
        path=entry.data[CONF_DBUS_APP_PATH],
        token=entry.data[CONF_DBUS_APP_TOKEN]
    )
    entry_data[BT_MESH_APPLICATION] = application

    # Function: process exception
    await application.dbus_connect()
    await application.connect()


    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # create a task to track changes in the mesh-cfgclient config file
#    async def reload_mesh_network_handler(hass):
#        """Reload Mesh network configuration task."""
#        while True:
    #        if mesh_cfgclient_conf.is_modified():
#            _LOGGER.debug("reload_mesh_network_handler(), config modified")
    #            #devices = await hass.async_add_executor_job(mesh_cfgclient_conf.load(), mesh_cfgclient_conf)
    #            devices = mesh_cfgclient_conf.load()
    #            # TODO: update mesh config

            #async_dispatcher_send(hass, f"{DOMAIN}_1234_sensor_add", None)
#            await asyncio.sleep(5)

#    hass.create_task(reload_mesh_network_handler(hass))

    # looking for new sensors on startup
    update_sensors_config_task = entry.async_create_background_task(
        hass,
        update_sensors_config(hass, entry, application),
        f"{DOMAIN}_{entry.title}_update_sensors_config"
    )


    # start Time Server
    application.time_server_init()

    await cleanup_device_registry(hass, mesh_cfgclient_conf)

    return True


#            device = device_registry.async_get_device(
#                identifiers={(DOMAIN, str(cfg_model.device.uuid))}
#            )


# FIXME: testing!!!!
async def update_sensors_config(
    hass: HomeAssistant,
    entry: ConfigEntry,
    app: BtMeshApplication
) -> None:
    entry_data = hass.data[DOMAIN][entry.entry_id]
    mesh_cfgclient_conf = entry_data[BT_MESH_CFGCLIENT_CONF]
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    mesh_cfg_model = mesh_cfgclient_conf.get_models(BtMeshModelId.SensorServer)[0]
    bt_mesh_entity = BtMeshEntity(app, mesh_cfg_model)
    _LOGGER.debug(bt_mesh_entity)

    processed_models = list()
    cfg_models = mesh_cfgclient_conf.get_models(BtMeshModelId.SensorServer)

    while (len(processed_models) < len(cfg_models)):
        for cfg_model in cfg_models:
            if cfg_model in processed_models:
#                _LOGGER.debug(f"SKIP DOMAIN={DOMAIN}, device_id={cfg_model.device.uuid}")
                continue

#            _LOGGER.debug(f"DOMAIN={DOMAIN}, device_id={cfg_model.device.uuid}")
            try:
                sensor_descriptors = await app.sensor_descriptor_get(
                    address=cfg_model.unicast_addr,
                    app_index=cfg_model.app_key,
                )

                for propery in sensor_descriptors:
                    property_id = int(propery['sensor_property_id'])
                    sensor_update_interval = int(round(propery['sensor_update_interval']))
                    async_dispatcher_send(
                        hass,
                        BT_MESH_DISCOVERY_ENTITY_NEW.format("sensor"),
                        app,
                        cfg_model,
                        property_id,
                        sensor_update_interval
                    )

                processed_models.append(cfg_model)

            except Exception as e:
                _LOGGER.debug("    fail to get descriptors for device %s, addr %04x: %s" % (cfg_model.device.uuid, cfg_model.device.unicast_addr, repr(e)))
                pass

        await asyncio.sleep(5)

    _LOGGER.debug(f"no new devices - exit")


async def cleanup_device_registry(hass: HomeAssistant, mesh_cfgclient_conf) -> None:
    """Remove deleted device registry entry if there are no remaining entities."""
#    entry_data = hass.data[DOMAIN][entry.entry_id]
#    mesh_cfgclient_conf = entry_data[BT_MESH_CFGCLIENT_CONF]
    device_registry = dr.async_get(hass)

    cfg_devices_uuid = [str(cfg_device.uuid) for cfg_device in mesh_cfgclient_conf.get_devices()]

    good = 0;
    bad = 0
#    devices = list()
    for dev_id, device_entry in list(device_registry.devices.items()):
        _LOGGER.debug(device_entry)
        for item in device_entry.identifiers:
            if item[0] == DOMAIN and item[1] not in cfg_devices_uuid:
                _LOGGER.debug(f"-------- drop device {dev_id} - {item[1]}")
                bad += 1
            elif item[0] == DOMAIN and item[1] in cfg_devices_uuid:
                _LOGGER.debug(f"++++++++ save device {dev_id} - {item[1]}")
                good +=1

    _LOGGER.debug(f"good={good}, bad={bad}")

#    _LOGGER.debug(f"all bt_mesh devices: {devices}")
#    entity_registry = er.async_get(hass)
#    for entity_id, entity_entry in list(entity_registry.entityes.items()):
#        _LOGGER.debug(entity_entry)
