"""BT Mesh integration."""
from __future__ import annotations

import asyncio
import voluptuous as vol
from typing import Final
from dataclasses import dataclass

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import config_validation as cv, device_registry as dr, entity_registry as er
from homeassistant.const import Platform
from homeassistant.helpers.storage import Store
from homeassistant.helpers.dispatcher import async_dispatcher_send

from bt_mesh_ctrl.mesh_cfgclient_conf import MeshCfgclientConf
from bt_mesh_ctrl import BtMeshModelId

from .application import BtMeshApplication

from .const import (
    DOMAIN,
    PLATFORMS,
    BT_MESH_CONFIG,
#    BT_MESH_APPLICATION,
#    BT_MESH_CFGCLIENT_CONF,
    CONF_DBUS_APP_PATH,
    CONF_DBUS_APP_TOKEN,
    CONF_MESH_CFGCLIENT_CONFIG_PATH,
    CONF_NODES,
    CONF_UNICAST_ADDR,
    CONF_SENSOR_DESCRIPTORS,
    CONF_PASSIVE,
    CONF_UPDATE_TIME,
    CONF_KEEPALIVE_TIME,
    DEFAULT_DBUS_APP_PATH,
    DEFAULT_MESH_CFGCLIENT_CONFIG_PATH,
    BT_MESH_DISCOVERY_ENTITY_NEW,
)

import logging
_LOGGER = logging.getLogger(__name__)


SENSOR_MODELS: Final = (
    BtMeshModelId.SensorServer,
    BtMeshModelId.SensorSetupServer
)


SENSOR_DESCRIPTOR_SCHEMA = vol.Schema(
    {
        vol.Required("sensor_property_id"): cv.positive_int,
        vol.Required("sensor_positive_tolerance"): cv.positive_int,
        vol.Required("sensor_negative_tolerance"): cv.positive_int,
        vol.Required("sensor_sampling_funcion"): cv.positive_int,
        vol.Required("sensor_measurement_period"): cv.positive_float,
        vol.Required("sensor_update_interval"): cv.positive_float,
    }
)

SENSOR_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_UPDATE_TIME): cv.positive_int,
        vol.Optional(CONF_KEEPALIVE_TIME): cv.positive_int,
        vol.Optional(CONF_SENSOR_DESCRIPTORS): vol.All(
            cv.ensure_list,
            [SENSOR_DESCRIPTOR_SCHEMA]
        ),
    }
)

NODE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_UPDATE_TIME): cv.positive_int,
        vol.Optional(CONF_KEEPALIVE_TIME): cv.positive_int,
        vol.Optional(CONF_PASSIVE, default=False): cv.boolean,
        vol.Optional("sensor", default={}): vol.Any(None, SENSOR_SCHEMA),
    },
    extra=vol.ALLOW_EXTRA
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_DBUS_APP_PATH, default=DEFAULT_DBUS_APP_PATH): cv.string,
                vol.Optional(CONF_MESH_CFGCLIENT_CONFIG_PATH, default=DEFAULT_MESH_CFGCLIENT_CONFIG_PATH): cv.string,
                vol.Optional(CONF_NODES, default={}): vol.Any(None, {cv.string: NODE_SCHEMA}),
            },
            extra=vol.ALLOW_EXTRA
        )
    },
    extra=vol.ALLOW_EXTRA
)



@dataclass
class BtMeshData:
    domain_conf: dict
    app: BtMeshApplication
    mesh_conf: MeshCfgclientConf
    discovered: list


type BtMeshConfigEntry = ConfigEntry[BtMeshData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up integration from config."""

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][BT_MESH_CONFIG] = config[DOMAIN]

    return True


async def async_setup_entry(hass: HomeAssistant, entry: BtMeshConfigEntry) -> bool:
    """Set up BT Mesh from a config entry."""

#    _LOGGER.debug(f"async_setup_entry(): entry_id={entry.entry_id}, entry_domain={entry.domain}, entry={entry.data}")
#    _LOGGER.debug(f"BT_MESH_CONFIG: {hass.data[DOMAIN][BT_MESH_CONFIG]}")
#    _LOGGER.debug(f"filename = {entry.data[CONF_MESH_CFGCLIENT_CONFIG_PATH]}")

    # create BtMesh application
    app = BtMeshApplication(
        hass,
        uuid=entry.entry_id,                    # FIXME: is not UUID
        path=entry.data[CONF_DBUS_APP_PATH],
        token=entry.data[CONF_DBUS_APP_TOKEN]
    )

    # create mesh network config
    mesh_conf = MeshCfgclientConf(
        filename=entry.data[CONF_MESH_CFGCLIENT_CONFIG_PATH]
    )

    entry.runtime_data = BtMeshData(
        domain_conf=hass.data[DOMAIN][BT_MESH_CONFIG],
        app=app,
        mesh_conf=mesh_conf,
        discovered=set()
    )

    # Function: process exception
    try:
        await app.dbus_connect()
        await app.connect()
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

    # FIXME: "track_mesh_conf_task" to constant
#    hass.data[DOMAIN][entry.entry_id]["track_mesh_conf_task"] = track_mesh_conf_task

    return True


async def track_mesh_conf(hass: HomeAssistant, entry: BtMeshConfigEntry):
    """The task of tracking changes to the configuration file and then 
       configuring new devices and removing unused ones."""
    devices_config_updated = True
    sensors_config_updated = True

    """Reload Mesh network configuration task."""
    while True:
        if entry.runtime_data.mesh_conf.is_modified():
            _LOGGER.debug("reload_mesh_network_handler(), config modified")
            try:
                await hass.async_add_executor_job(entry.runtime_data.mesh_conf.load)
                devices_config_updated = False
                sensors_config_updated = False
            except FileNotFoundError:
                _LOGGER.error(f"Mesh Network config file not found:")
                pass

        # looking for a new devices on startup
        if not devices_config_updated:
            devices_config_updated = await load_devices_config(hass, entry)

        # looking for a new sensors on startup
        if not sensors_config_updated:
            sensors_config_updated = await load_sensors_config(hass, entry)

        # remove unbinded models and unprovisioned devices
        await cleanup_device_registry(hass, entry)

#        await cleanup_entity_registry(hass, entry)

        await asyncio.sleep(5)


async def load_devices_config(hass: HomeAssistant, entry: BtMeshConfigEntry) -> bool:
    """Loading node models (except the sensor) from the config and adding them to the HA."""
    mesh_conf = entry.runtime_data.mesh_conf
    _LOGGER.debug(f"load_devices_config(): start, {entry.runtime_data.domain_conf}")

    for cfg_model in mesh_conf.get_models():
        _LOGGER.debug(f"model: model_id={cfg_model.model_id}, {cfg_model.unique_id}")

        # sensor model is loaded in dedicated task
        if cfg_model.model_id in SENSOR_MODELS:
            _LOGGER.debug(f"    skip sensor")
            continue

        # skip already discovered devices
        if cfg_model.unique_id in entry.runtime_data.discovered:
            _LOGGER.debug(f"    {cfg_model.unique_id} already discovered")
            continue

        try:
            node_conf = entry.runtime_data.domain_conf[CONF_NODES][f"{cfg_model.unicast_addr:04x}"]
        except KeyError:
            node_conf = {}

        async_dispatcher_send(
            hass,
            BT_MESH_DISCOVERY_ENTITY_NEW.format(cfg_model.model_id),
            *(entry.runtime_data.app, cfg_model, node_conf)
        )

        entry.runtime_data.discovered.add(cfg_model.unique_id)

    return True


async def load_sensors_config(hass: HomeAssistant, entry: BtMeshConfigEntry) -> bool:
    """Loading sensor models (except the sensor) from the config and adding them to the HA."""
    app = entry.runtime_data.app
    mesh_conf = entry.runtime_data.mesh_conf

    # get descriptors from config
    descriptors_conf = dict()
    if CONF_NODES in entry.runtime_data.domain_conf:
        descriptors_conf = {
            unicast_addr: node_conf[Platform.SENSOR][CONF_SENSOR_DESCRIPTORS]
                for unicast_addr, node_conf in entry.runtime_data.domain_conf[CONF_NODES].items()
                    if Platform.SENSOR in node_conf and \
                        node_conf[Platform.SENSOR] is not None and \
                        CONF_SENSOR_DESCRIPTORS in node_conf[Platform.SENSOR]
        }

    # get descriptors from persistent storage
    descriptors_store: Store[dict[int, Any]] = Store(hass, 1, "bt_mesh.sensor_descriptors")
    descriptors = await descriptors_store.async_load()

    _LOGGER.debug(f"load_sensors_config(): start")

    cfg_models = []
    for model_id in SENSOR_MODELS:
        cfg_models.extend(mesh_conf.get_models_by_model_id(model_id))
    _LOGGER.debug(f"load_sensors_config(): {cfg_models}")

    result = True
    for cfg_model in cfg_models:
        unicast_addr_key = f"{cfg_model.unicast_addr:04x}"
        _LOGGER.debug(f"sensor: unicast_addr={cfg_model.unicast_addr:04x} model_id={cfg_model.model_id:04x}, {cfg_model.unique_id}")

        # skip already discovered devices
        if cfg_model.unique_id in entry.runtime_data.discovered:
            _LOGGER.debug(f"    {cfg_model.unique_id} already discovered")
            continue

        try:
            node_conf = entry.runtime_data.domain_conf[CONF_NODES][f"{cfg_model.unicast_addr:04x}"]
        except KeyError:
            node_conf = {}

        # get descriptors from config
        if unicast_addr_key in descriptors_conf:
            _LOGGER.debug("    get descriptors from config")
            sensor_descriptors = descriptors_conf[unicast_addr_key]
        # get descriptors from local storage
        elif descriptors is not None and unicast_addr_key in descriptors:
            _LOGGER.debug("    get descriptors from local storage")
            sensor_descriptors = descriptors[unicast_addr_key]
        # get descriptors from device
        else:
            _LOGGER.debug("    get descriptors from device")
            _sensor_descriptors = await app.sensor_descriptor_get(
                destination=cfg_model.unicast_addr,
                app_index=cfg_model.app_key,
            )
            sensor_descriptors = [
                {
                    "sensor_property_id": propery.sensor_property_id,
                    "sensor_positive_tolerance": propery.sensor_positive_tolerance,
                    "sensor_negative_tolerance": propery.sensor_negative_tolerance,
                    "sensor_sampling_funcion": propery.sensor_sampling_funcion,
                    "sensor_measurement_period": propery.sensor_measurement_period,
                    "sensor_update_interval": propery.sensor_update_interval,
                }
                for propery in _sensor_descriptors
            ] if _sensor_descriptors else None

        if sensor_descriptors:
            descriptors[unicast_addr_key] = sensor_descriptors

            for propery in sensor_descriptors:
                property_id = int(propery["sensor_property_id"])

                async_dispatcher_send(
                    hass,
                    BT_MESH_DISCOVERY_ENTITY_NEW.format(cfg_model.model_id),
                    *(entry.runtime_data.app, cfg_model, propery, node_conf)
                )

            # mark model discovered
            entry.runtime_data.discovered.add(cfg_model.unique_id)
        else:
            _LOGGER.debug(f"fail to get descriptors for device {cfg_model.device.unicast_addr:04x}")
            result = False

    # save updated descriptors to persistent strage
    await descriptors_store.async_save(descriptors)

    _LOGGER.debug(f"load_sensors_config(): finished, result={result}")

    return result


async def cleanup_entity_registry(hass: HomeAssistant, entry: BtMeshConfigEntry) -> None:
    """...."""
    mesh_conf =  entry.runtime_data.mesh_conf

    cfg_models = mesh_conf.get_models()

    entity_reg = er.async_get(hass)
    entries = er.async_entries_for_config_entry(entity_reg, entry.entry_id)
    for reg_entry in entries:
        _LOGGER.debug(f"cleanup_entity_registry() {reg_entry.unique_id}")
        pass


async def cleanup_device_registry(hass: HomeAssistant, entry: BtMeshConfigEntry) -> None:
    """Remove deleted device registry entry if there are no remaining entities."""
    mesh_conf =  entry.runtime_data.mesh_conf
    device_registry = dr.async_get(hass)

    provisioned_devices: set[str] = set(
        [str(cfg_device.unique_id) for cfg_device in mesh_conf.get_devices()]
    )

    device_registry = dr.async_get(hass)
    for device_entry in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        for identifier in device_entry.identifiers:
            if identifier[0] == DOMAIN and identifier[1] not in provisioned_devices:
                device_registry.async_remove_device(device_entry.id)
                _LOGGER.debug(f"cleanup_device_registry(): removed_devices, id={device_entry.id}, identifier={identifier[1]}")


async def async_unload_entry(hass: HomeAssistant, entry: BtMeshConfigEntry) -> bool:
    """Unloading the BT Mesh platforms."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        app = entry.runtime_data.app
        await app.dbus_disconnect()
    return unload_ok
