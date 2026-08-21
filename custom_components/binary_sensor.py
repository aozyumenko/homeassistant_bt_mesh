"""BT MESH binary sensor integration"""

from typing import Union, Callable
from uuid import UUID

from bluetooth_mesh.messages.properties import PropertyID
from bluetooth_mesh.messages.sensor import SensorOpcode
from bluetooth_mesh.utils import ParsedMeshMessage

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import (
    Platform,
)

from bt_mesh_ctrl import BtMeshModelId, BtMeshOpcode
from bt_mesh_ctrl.mesh_cfgclient_conf import MeshCfgModel

from .application import BtMeshApplication
from .entity import BtMeshEntity, ClassNotFoundError
from .const import (
    BT_MESH_DISCOVERY_ENTITY_NEW,
    CONF_UPDATE_TIME,
    CONF_KEEPALIVE_TIME,
    CONF_PASSIVE,
)

import logging
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigType,
    async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Set up the BT MESH sensor entry."""

    @callback
    def async_add_binary_sensor(
        app: BtMeshApplication,
        cfg_model: MeshCfgModel,
        propery: dict,
        node_conf: dict
    ) -> None:
        property_id = PropertyID(propery["sensor_property_id"])
        update_interval = float(propery["sensor_update_interval"])

        platform_conf = node_conf.get(Platform.SENSOR, None) or {}
        update_timeout = platform_conf.get(
            CONF_UPDATE_TIME,
            node_conf.get(CONF_UPDATE_TIME, update_interval)
        )
        invalidate_timeout = platform_conf.get(
            CONF_KEEPALIVE_TIME,
            node_conf.get(CONF_KEEPALIVE_TIME, update_interval * 2.5)
        )
        passive = node_conf.get(CONF_PASSIVE, False)

        try:
            sensor_entity = BtMeshBinarySensorEntityFactory.get(property_id)(
                app=app,
                cfg_model=cfg_model,
                update_timeout=update_timeout,
                invalidate_timeout=invalidate_timeout,
                passive=passive
            )
            async_add_entities([sensor_entity])
        except ClassNotFoundError:
            pass

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            BT_MESH_DISCOVERY_ENTITY_NEW.format(BtMeshModelId.SensorServer),
            async_add_binary_sensor,
        )
    )
    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            BT_MESH_DISCOVERY_ENTITY_NEW.format(BtMeshModelId.SensorSetupServer),
            async_add_binary_sensor,
        )
    )

    return True


# BT Mesh Sensor Server
class BtMeshBinarySensorEntity(BtMeshEntity, BinarySensorEntity):
    """Base class for Bluetooth Mesh sensor entity."""

    property_id: PropertyID
    argument_keys: list

    status_opcodes = (
        SensorOpcode.SENSOR_STATUS,
        SensorOpcode.SENSOR_DESCRIPTOR_STATUS,
    )

    def __init__(self, *args, **kwargs) -> None:
        BtMeshEntity.__init__(self, *args, **kwargs)

        # update sensor unique_id and name attributes
        self._attr_unique_id = BtMeshEntity.unique_id_sensor(self.cfg_model, self.property_id)
        self._attr_name = BtMeshEntity.name_sensor(self.cfg_model, self.property_id)

    def receive_message(
        self,
        source: int,
        app_index: int,
        destination: Union[int, UUID],
        message: ParsedMeshMessage
    ):
        """Receive status reports from Sensor model."""
        opcode_name = BtMeshOpcode.get(message.opcode).name.lower()
        match message.opcode:
            case SensorOpcode.SENSOR_STATUS:
                for property in message[opcode_name]:
                    if property.sensor_setting_property_id == self.property_id:
                        self.update_model_state(property)
                        break
            case _:
                pass

    async def query_model_state(self) -> any:
        """Query sensor state."""
        return await self.app.sensor_get(
            destination=self.unicast_addr,
            app_index=self.app_key,
            property_id=self.property_id,
        )

    async def sensor_get(self):
        """Extract sensor value from response."""
        try:
            prop = self.model_state
            _LOGGER.debug(f"prop={prop}")
            for key in self.argument_keys:
                prop = prop[key]
            return bool(prop)
        except TypeError:
            pass
        except Exception as e:
            _LOGGER.error(f"BtMeshSensor: sensor_get(): {e}")
            return None

    async def async_update(self) -> None:
        """Fetch new state data for the sensor."""
        self._attr_is_on = await self.sensor_get()
        self._attr_available = self._attr_is_on is not None


class BtMeshSensor_PresenceDetected(BtMeshBinarySensorEntity):
    """Presence Detected sensor"""

    property_id = PropertyID.PRESENCE_DETECTED
    argument_keys = ["presence_detected", "presence_detected"]


class BtMeshBinarySensorEntityFactory(object):
    @staticmethod
    def get(property_id: PropertyID) -> object:
        if type(property_id) is not PropertyID:
            raise ValueError("property_id must be PropertyID")

        raw_subclasses_ = BtMeshBinarySensorEntity.__subclasses__()
        classes: dict[int, Callable[..., object]] = {c.property_id: c for c in raw_subclasses_}
        class_ = classes.get(property_id, None)
        if class_ is not None:
            return class_

        raise ClassNotFoundError
