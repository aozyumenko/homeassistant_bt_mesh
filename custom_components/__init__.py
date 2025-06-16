"""BT Mesh integration."""
from __future__ import annotations


import asyncio
import voluptuous as vol
from typing import Final

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import config_validation as cv, device_registry as dr, entity_registry as er
#from homeassistant.helpers import async_entries_for_label
from homeassistant.const import Platform

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
    BT_MESH_ALREADY_DISCOVERED,
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


MODEL_ID_PLATFROM: Final = {
    BtMeshModelId.GenericOnOffServer: Platform.SWITCH,
#    BtMeshModelId.GenericLevelServer: Platform.COVER,
    BtMeshModelId.GenericBatteryServer: BtMeshModelId.get_name(BtMeshModelId.GenericBatteryServer),
    BtMeshModelId.SensorServer: Platform.SENSOR,
#    BtMeshModelId.LightLightnessSetupServer: Platform.LIGHT,
#    BtMeshModelId.LightCTLSetupServer: Platform.LIGHT,
#    BtMeshModelId.LightHSLSetupServer: Platform.LIGHT,
#    BtMeshModelId.ThermostatServer: Platform.LIGHT,
}



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

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][BT_MESH_CONFIG] = config[DOMAIN]

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BT Mesh from a config entry."""

#    _LOGGER.debug("async_setup_entry(): entry_id=%s, entry_domain=%s, entry=%s" % (entry.entry_id, entry.domain, entry.data))

    _LOGGER.debug(f"BT_MESH_CONFIG: {hass.data[DOMAIN][BT_MESH_CONFIG]}")
    _LOGGER.debug(f"filename = {entry.data[CONF_MESH_CFGCLIENT_CONFIG_PATH]}")

    # create mesh network config
    mesh_conf = MeshCfgclientConf(
        filename=entry.data[CONF_MESH_CFGCLIENT_CONFIG_PATH]
    )

    # create BtMesh application
    application = BtMeshApplication(
        hass,
        uuid = entry.entry_id,
        path=entry.data[CONF_DBUS_APP_PATH],
        token=entry.data[CONF_DBUS_APP_TOKEN]
    )

    hass.data[DOMAIN][entry.entry_id] = {
        BT_MESH_CFGCLIENT_CONF: mesh_conf,
        BT_MESH_APPLICATION: application,
        BT_MESH_ALREADY_DISCOVERED: [],
    }

    # Function: process exception
    try:
        await application.dbus_connect()
        await application.connect()
    except Exception as e:
        _LOGGER.error(f"Failed to connect to dBUS: {e}")
        return False

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


    # run task to track modifications to the Bt Mesh configuration file
    track_mesh_conf_task = entry.async_create_background_task(
        hass,
        track_mesh_conf(hass, entry),
        f"{DOMAIN}_{entry.title}_track_mesh_conf"
    )

    return True


async def track_mesh_conf(
    hass: HomeAssistant,
    entry: ConfigEntry,
):
    app = hass.data[DOMAIN][entry.entry_id][BT_MESH_APPLICATION]
    mesh_conf = hass.data[DOMAIN][entry.entry_id][BT_MESH_CFGCLIENT_CONF]

    """Reload Mesh network configuration task."""
    while True:
        if mesh_conf.is_modified():
            _LOGGER.debug("reload_mesh_network_handler(), config modified")
            try:
                await hass.async_add_executor_job(mesh_conf.load)
            except Exception as e:
                _LOGGER.error(f"Fail to load Mesh Network config: {e}")


            # looking for a new devices on startup
            load_devices_config_task = entry.async_create_background_task(
                hass,
                load_devices_config(hass, entry),
                f"{DOMAIN}_{entry.title}_load_devices_config"
            )

            # looking for a new sensors on startup
            load_sensors_config_task = entry.async_create_background_task(
                hass,
                load_sensors_config(hass, entry),
                f"{DOMAIN}_{entry.title}_load_sensors_config"
            )

            # TODO: wait
            await asyncio.wait((load_devices_config_task, load_sensors_config_task))

            # TODO: remove unused devices
            await cleanup_device_registry(hass, entry)

        await asyncio.sleep(5)


async def load_devices_config(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    app = hass.data[DOMAIN][entry.entry_id][BT_MESH_APPLICATION]
    mesh_conf = hass.data[DOMAIN][entry.entry_id][BT_MESH_CFGCLIENT_CONF]

    cfg_models = mesh_conf.get_models()

    _LOGGER.debug("load_devices_config(): start")

    for cfg_model in cfg_models:
        _LOGGER.debug(f"model: model_id={cfg_model.model_id}, {cfg_model.unique_id}")

        if cfg_model.model_id == BtMeshModelId.SensorServer:
            _LOGGER.debug(f"    skip sensor")
            continue

        if cfg_model.unique_id in hass.data[DOMAIN][entry.entry_id][BT_MESH_ALREADY_DISCOVERED]:
            _LOGGER.debug("    {cfg_model.unique_id} already discovered")
            continue

        if cfg_model.model_id in MODEL_ID_PLATFROM:
            _LOGGER.debug(f"    send {BT_MESH_DISCOVERY_ENTITY_NEW.format(MODEL_ID_PLATFROM[cfg_model.model_id])}")
            async_dispatcher_send(
                hass,
                BT_MESH_DISCOVERY_ENTITY_NEW.format(MODEL_ID_PLATFROM[cfg_model.model_id]),
                app,
                cfg_model,
            )
            hass.data[DOMAIN][entry.entry_id][BT_MESH_ALREADY_DISCOVERED].append(cfg_model.unique_id)
        else:
            _LOGGER.debug(f"    {cfg_model.model_id} not in platform")


async def load_sensors_config(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    app = hass.data[DOMAIN][entry.entry_id][BT_MESH_APPLICATION]
    mesh_conf = hass.data[DOMAIN][entry.entry_id][BT_MESH_CFGCLIENT_CONF]

    _LOGGER.debug("load_sensors_config(): start")

    cfg_models = mesh_conf.get_models_by_model_id(BtMeshModelId.SensorServer)

    while (True):
        repeat = False
        for cfg_model in cfg_models:
            _LOGGER.debug(f"sensor: model_id={cfg_model.model_id}, {cfg_model.unique_id}")

            if cfg_model.unique_id in hass.data[DOMAIN][entry.entry_id][BT_MESH_ALREADY_DISCOVERED]:
                _LOGGER.debug(f"    {cfg_model.unique_id} already discovered")
                continue

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
                        BT_MESH_DISCOVERY_ENTITY_NEW.format(MODEL_ID_PLATFROM[BtMeshModelId.SensorServer]),
                        app,
                        cfg_model,
                        property_id,
                        sensor_update_interval
                    )

                hass.data[DOMAIN][entry.entry_id][BT_MESH_ALREADY_DISCOVERED].append(cfg_model.unique_id)

            except Exception as e:
                _LOGGER.debug("    fail to get descriptors for device %s, addr %04x: %s" % (cfg_model.device.uuid, cfg_model.device.unicast_addr, repr(e)))
                repeat = True
                pass

        _LOGGER.debug(f"repeat={repeat}")
        if not repeat:
            break

        await asyncio.sleep(5)

    _LOGGER.debug(f"no new devices - exit")


async def cleanup_device_registry(
    hass: HomeAssistant,
    entry: ConfigEntry
) -> None:
    """Remove deleted device registry entry if there are no remaining entities."""

    app = hass.data[DOMAIN][entry.entry_id][BT_MESH_APPLICATION]
    mesh_conf = hass.data[DOMAIN][entry.entry_id][BT_MESH_CFGCLIENT_CONF]

    device_registry = dr.async_get(hass)

    cfg_devices_uuid = [str(cfg_device.uuid) for cfg_device in mesh_conf.get_devices()]

    good = 0;
    bad = 0
    devices = list()
    for dev_id, device_entry in list(device_registry.devices.items()):
#        _LOGGER.debug(device_entry)
        for item in device_entry.identifiers:
            if item[0] == DOMAIN and item[1] not in cfg_devices_uuid:
                _LOGGER.debug(f"-------- drop device {dev_id} - {item[1]}")
                bad += 1
            elif item[0] == DOMAIN and item[1] in cfg_devices_uuid:
                _LOGGER.debug(f"++++++++ save device {dev_id} - {item[1]}")
                good +=1

    _LOGGER.debug(f"good={good}, bad={bad}")

    pass