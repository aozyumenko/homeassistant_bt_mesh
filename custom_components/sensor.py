"""BT MESH sensor integration"""
from __future__ import annotations

import asyncio

from construct import Container

from bluetooth_mesh.messages.properties import PropertyID
from bluetooth_mesh.messages.generic.battery import GenericBatteryOpcode
from bluetooth_mesh.messages.sensor import SensorOpcode
from bluetooth_mesh.models.generic.battery import GenericBatteryClient
from bluetooth_mesh.models.sensor import SensorClient

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
    SensorEntityDescription,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfPower,
    UnitOfTemperature,
    Platform,
)

from bt_mesh_ctrl import BtMeshModelId, BtSensorAttrPropertyId, BtMeshOpcode
from bt_mesh_ctrl.mesh_cfgclient_conf import MeshCfgModel

from .application import BtMeshApplication
from .entity import BtMeshEntity, ClassNotFoundError
from .const import (
    BT_MESH_DISCOVERY_ENTITY_NEW,
    BT_MESH_MSG,
    CONF_UPDATE_TIME,
    CONF_KEEPALIVE_TIME,
    CONF_PASSIVE,
    G_MESH_CACHE_UPDATE_TIMEOUT,
    G_MESH_CACHE_INVALIDATE_TIMEOUT,
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
    def async_add_generic_battery(
        app: BtMeshApplication,
        cfg_model: MeshCfgModel,
        node_conf: dict
    ) -> None:
        platform_conf = node_conf.get(Platform.SENSOR, None) or {}
        update_timeout = platform_conf.get(CONF_UPDATE_TIME, \
            node_conf.get(CONF_UPDATE_TIME, G_MESH_CACHE_UPDATE_TIMEOUT))
        invalidate_timeout = platform_conf.get(CONF_KEEPALIVE_TIME, \
            node_conf.get(CONF_KEEPALIVE_TIME, G_MESH_CACHE_INVALIDATE_TIMEOUT))
        passive = node_conf.get(CONF_PASSIVE, False)

        async_add_entities(
            [
                BtMeshGenericBatteryEntity(
                    app=app,
                    cfg_model=cfg_model,
                    update_timeout=update_timeout,
                    invalidate_timeout=invalidate_timeout,
                    passive=passive
                )
            ]
        )

    @callback
    def async_add_sensor(
        app: BtMeshApplication,
        cfg_model: MeshCfgModel,
        propery: dict,
        node_conf: dict
    ) -> None:
        property_id = PropertyID(propery["sensor_property_id"])
        update_interval = float(propery["sensor_update_interval"])

        platform_conf = node_conf.get(Platform.SENSOR, None) or {}
        update_timeout = platform_conf.get(CONF_UPDATE_TIME, \
            node_conf.get(CONF_UPDATE_TIME, update_interval))
        invalidate_timeout = platform_conf.get(CONF_KEEPALIVE_TIME, \
            node_conf.get(CONF_KEEPALIVE_TIME, update_interval * 2.5))
        passive = node_conf.get(CONF_PASSIVE, False)

        try:
            sensor_entity = BtMeshSensorEntityFactory.get(property_id)(
                app=app,
                cfg_model=cfg_model,
                update_timeout=update_timeout,
                invalidate_timeout=invalidate_timeout,
                passive=passive
            )
            async_add_entities([sensor_entity])
        except ClassNotFoundError as e:
            _LOGGER.error(f"failed to create BtMeshSensorEntity {cfg_model.unicast_addr}.{property_id:04x}: {repr(e)}")

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            BT_MESH_DISCOVERY_ENTITY_NEW.format(BtMeshModelId.GenericBatteryServer),
            async_add_generic_battery,
        )
    )
    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            BT_MESH_DISCOVERY_ENTITY_NEW.format(BtMeshModelId.SensorServer),
            async_add_sensor,
        )
    )
    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            BT_MESH_DISCOVERY_ENTITY_NEW.format(BtMeshModelId.SensorSetupServer),
            async_add_sensor,
        )
    )

    return True


# BT Mesh Generic Battery Server
class BtMeshGenericBatteryEntity(BtMeshEntity, SensorEntity):
    """Class for Bluetooth Mesh Generic Battery sensor."""

    entity_description = SensorEntityDescription(
        key="battery_level",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        name="Battery Level",
    )

    status_opcodes = (
        GenericBatteryOpcode.GENERIC_BATTERY_STATUS,
    )

    async def query_model_state(self) -> any:
        """Query GenericBattery state."""
        return await self.app.generic_battery_get(
            destination=self.unicast_addr,
            app_index=self.app_key,
        )

    async def async_update(self) -> None:
        """Fetch new state data for the sensor."""
        self._attr_native_value = self.model_state.battery_level \
            if self.model_state is not None else None
        self._attr_available = self._attr_native_value is not None


# BT Mesh Sensor Server
class BtMeshSensorEntity(BtMeshEntity, SensorEntity):
    """Base class for Bluetooth Mesh sensor entity."""

    property_id: PropertyID
    argument_keys: list
    argument_round = 2

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
                        #self.update_model_state_thr(property)
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
            for key in self.argument_keys:
                prop = prop[key]
            return round(float(prop), self.argument_round)
        except TypeError:
            pass
        except Exception as e:
            _LOGGER.error(f"BtMeshSensor: sensor_get(): {e}")
            return None

    async def async_update(self) -> None:
        """Fetch new state data for the sensor."""
        self._attr_native_value = await self.sensor_get()
        self._attr_available = self._attr_native_value is not None


class BtMeshSensor_PresentDeviceInputPower(BtMeshSensorEntity):
    """Present Input Power sensor"""

    property_id = PropertyID.PRESENT_DEVICE_INPUT_POWER
    entity_description = SensorEntityDescription(
        key="present_device_input_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        name="Power",
    )
    argument_keys = ["present_device_input_power", "power"]


class BtMeshSensor_PresentInputCurrent(BtMeshSensorEntity):
    """Present Input Current sensor."""

    property_id = PropertyID.PRESENT_INPUT_CURRENT
    entity_description = SensorEntityDescription(
        key="present_input_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Current",
    )
    argument_keys = ["present_input_current", "current"]


class BtMeshSensor_PreciseTotalDeviceEnergyUse(BtMeshSensorEntity):
    """Energy Use sensor."""

    property_id = PropertyID.PRECISE_TOTAL_DEVICE_ENERGY_USE
    entity_description = SensorEntityDescription(
        key="totalenergy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        name="Total Energy",
    )
    argument_keys = ["precise_total_device_energy_use", "energy"]


class BtMeshSensor_PresentInputVoltage(BtMeshSensorEntity):
    """Input Voltage sensor"""

    property_id = PropertyID.PRESENT_INPUT_VOLTAGE
    entity_description = SensorEntityDescription(
        key="present_input_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        name="Voltage",
    )
    argument_keys = ["present_input_voltage", "voltage"]


class BtMeshSensor_Desired_Ambient_Temperature(BtMeshSensorEntity):
    """Desired Ambient Temperatire sensor"""

    property_id = PropertyID.DESIRED_AMBIENT_TEMPERATURE
    entity_description = SensorEntityDescription(
        key="desired_ambient_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        name="Desired ambient temperatire",
    )
    argument_keys = ["desired_ambient_temperature", "temperature"]


class BtMeshSensor_Precise_Present_Ambient_Temperature(BtMeshSensorEntity):
    """Ambient Temperature sensor"""

    property_id = PropertyID.PRECISE_PRESENT_AMBIENT_TEMPERATURE
    entity_description = SensorEntityDescription(
        key="precise_present_ambient_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        name="Ambient temperatire",
    )
    argument_keys = ["precise_present_ambient_temperature", "temperature"]

class BtMeshSensor_Precise_Present_Ambient_Temperature(BtMeshSensorEntity):
    """Ambient Temperature sensor"""

    property_id = PropertyID.PRECISE_PRESENT_AMBIENT_TEMPERATURE
    entity_description = SensorEntityDescription(
        key="precise_present_ambient_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        name="Ambient temperatire",
    )
    argument_keys = ["precise_present_ambient_temperature", "temperature"]

class BtMeshSensor_Present_Ambient_Relative_Humidity(BtMeshSensorEntity):
    """Ambient Humidity sensor"""

    property_id = PropertyID.PRESENT_AMBIENT_RELATIVE_HUMIDITY
    entity_description = SensorEntityDescription(
        key="present_ambient_relative_humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Ambient humidity",
    )
    argument_keys = ["present_ambient_relative_humidity", "humidity"]

class BtMeshSensor_Present_Indoor_Relative_Humidity(BtMeshSensorEntity):
    """Indoor Humidity sensor"""

    property_id = PropertyID.PRESENT_INDOOR_RELATIVE_HUMIDITY
    entity_description = SensorEntityDescription(
        key="present_indoor_relative_humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Indoor humidity",
    )
    argument_keys = ["present_indoor_relative_humidity", "humidity"]

class BtMeshSensor_Present_Outdoor_Relative_Humidity(BtMeshSensorEntity):
    """Outdoor Humidity sensor"""

    property_id = PropertyID.PRESENT_OUTDOOR_RELATIVE_HUMIDITY
    entity_description = SensorEntityDescription(
        key="present_outdoor_relative_humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Outdoor humidity",
    )
    argument_keys = ["present_outdoor_relative_humidity", "humidity"]


class BtMeshSensorEntityFactory(object):
    @staticmethod
    def get(property_id: PropertyID) -> object:
        if type(property_id) != PropertyID:
            raise ValueError("property_id must be PropertyID")

        raw_subclasses_ = BtMeshSensorEntity.__subclasses__()
        classes: dict[int, Callable[..., object]] = {c.property_id:c for c in raw_subclasses_}
        class_ = classes.get(property_id, None)
        if class_ is not None:
            return class_

        raise ClassNotFoundError
