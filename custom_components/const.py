"""Constants for the Bluetooth Mesh client integration."""


from typing import Final
from homeassistant.const import Platform


DOMAIN: Final = "bt_mesh"
PLATFORMS: Final = (
    Platform.SWITCH,
)

DBUS_APP_PATH: Final = "/mesh/homeassistant/client0"
MESH_CFGCLIENT_CONFIG_PATH = "~/.config/meshcfg/config_db.json"

BT_MESH_CONFIG: Final = "config"
BT_MESH_APPLICATION: Final = "application"
BT_MESH_CFGCLIENT_CONF = "mesh_cfgclient_conf"

# FIXME: drop
CONF_APP_KEY: Final = "app_key"
