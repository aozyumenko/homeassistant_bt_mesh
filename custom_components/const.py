"""Constants for the Bluetooth Mesh client integration."""
from __future__ import annotations

from typing import Final
from homeassistant.const import Platform


DOMAIN: Final = "bt_mesh"
PLATFORMS: Final = (
    Platform.SWITCH,
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.CLIMATE,
)


BT_MESH_DISCOVERY_ENTITY_NEW: Final = "bt_mesh_discovery_entity_new.{}"
BT_MESH_MSG: Final = "bt_mesh_msg.{:x}_{:x}"
BT_MESH_INVALIDATE: Final = "bt_mesh_invalidate.{:x}"

# domain data keys
BT_MESH_CONFIG: Final = "config"
#BT_MESH_APPLICATION: Final = "application"
#BT_MESH_CFGCLIENT_CONF: Final = "mesh_cfgclient_conf"
#BT_MESH_ALREADY_DISCOVERED: Final = "bt_mesh_already_discovered"

# config keys
CONF_DBUS_APP_PATH: Final = "dbus_app_path"
CONF_DBUS_APP_TOKEN: Final = "dbus_app_token"
CONF_MESH_CFGCLIENT_CONFIG_PATH: Final = "cfgclient_config_path"
CONF_NODES: Final = "nodes"
CONF_UNICAST_ADDR: Final = "unicast_addr"
CONF_SENSOR_DESCRIPTORS: Final = "sensor_descriptors"
CONF_PASSIVE: Final = "passive"
CONF_UPDATE_TIME: Final = "update_time"
CONF_KEEPALIVE_TIME: Final = "keepalive_time"

STORAGE_SENSOR_DESCRIPTORS:Final = "bt_mesh.sensor_descriptors"

# config file defaults
DEFAULT_DBUS_APP_PATH: Final = "/mesh/homeassistant/client0"
DEFAULT_MESH_CFGCLIENT_CONFIG_PATH: Final = "~/.config/meshcfg/config_db.json"
DEFAULT_MESH_JOIN_TIMEOUT: Final = 120

DEFAULT_LIGHT_BRIGHTNESS: Final = 128
DEFAULT_LIGHT_TEMPERATURE: Final = 4600

# Mesh application config
G_TIMEOUT: Final = 0.6
G_SEND_INTERVAL: Final = 0.2
G_UNACK_RETRANSMISSIONS: Final = 3
G_UNACK_INTERVAL: Final = 0.05

G_MESH_CACHE_UPDATE_TIMEOUT: Final = 15
G_MESH_CACHE_INVALIDATE_TIMEOUT: Final = 360
