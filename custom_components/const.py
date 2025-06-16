"""Constants for the Bluetooth Mesh client integration."""
from __future__ import annotations

from typing import Final
from homeassistant.const import Platform


DOMAIN: Final = "bt_mesh"
PLATFORMS: Final = (
#    Platform.SWITCH,
    Platform.SENSOR,
#    Platform.LIGHT,
#    Platform.CLIMATE,
)


BT_MESH_DISCOVERY_ENTITY_NEW = "bt_mesh_discovery_entity_new.{}"


# domain data keys
BT_MESH_CONFIG: Final = "config"
BT_MESH_APPLICATION: Final = "application"
BT_MESH_CFGCLIENT_CONF: Final = "mesh_cfgclient_conf"
BT_MESH_ALREADY_DISCOVERED: Final = "bt_mesh_already_discovered"


# config keys
CONF_DBUS_APP_PATH = "dbus_app_path"
CONF_DBUS_APP_TOKEN: Final = "dbus_app_token"
CONF_MESH_CFGCLIENT_CONFIG_PATH = "cfgclient_config_path"


# config file defaults
DEFAULT_DBUS_APP_PATH: Final = "/mesh/homeassistant/client0"
DEFAULT_MESH_CFGCLIENT_CONFIG_PATH = "~/.config/meshcfg/config_db.json"
DEFAULT_MESH_JOIN_TIMEOUT = 120


# Mesh application config
#G_TIMEOUT = 3.0
#G_SEND_INTERVAL = 0.5
G_TIMEOUT = 0.15
G_SEND_INTERVAL = 0.05
G_UNACK_RETRANSMISSIONS = 3
G_UNACK_INTERVAL = 0.05
G_MESH_SENSOR_CACHE_TIMEOUT = 60

G_MESH_CACHE_UPDATE_TIMEOUT = 15
G_MESH_CACHE_INVALIDATE_TIMEOUT = 360
