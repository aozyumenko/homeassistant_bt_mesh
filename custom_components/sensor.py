"""BT MESH sensor integration"""
from __future__ import annotations

#import asyncio

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
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.const import Platform

from bluetooth_mesh.messages.properties import PropertyID

from .bt_mesh.mesh_cfgclient_conf import MeshCfgModel
from .bt_mesh.entity import BtMeshEntity
from .bt_mesh import BtMeshModelId, BtSensorAttrPropertyId
from .const import DOMAIN, BT_MESH_APPLICATION, BT_MESH_DISCOVERY_ENTITY_NEW

import logging
_LOGGER = logging.getLogger(__name__)



async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigType,
    async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Set up the BT MESH sensor entry."""

    @callback
    def async_add_sensor(
        app: BtMeshApplication,
        cfg_model: MeshCfgModel,
        property_id: PropertyID,
        update_period: int
    ) -> None:
#        _LOGGER.debug("async_add_sensor(): uuid=%s, addr=0x%04x, app_key=%d, property_id=0x%x, update_period=%d" % (cfg_model.device.uuid, cfg_model.unicast_addr, cfg_model.app_key, property_id, update_period))
        try:
            sensor_entity = BtMeshSensorEntityFactory.get(property_id)(
                app,
                cfg_model,
                update_period
            )
            async_add_entities([sensor_entity])
#            _LOGGER.debug(f"sensor_entity = {sensor_entity}")
        except Exception as e:
#            _LOGGER.debug(f"failed to create BtMeshSensorEntity: {e}")
            pass


    @callback
    def async_add_generic_battery(
        app: BtMeshApplication,
        cfg_model: MeshCfgModel
    ) -> None:
        _LOGGER.debug("async_add_generic_battery(): uuid=%s, addr=0x%04x, app_key=%d" % (cfg_model.device.uuid, cfg_model.unicast_addr, cfg_model.app_key))
        async_add_entities([BtMeshGenericBatteryEntity(app, cfg_model)])


    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            BT_MESH_DISCOVERY_ENTITY_NEW.format(Platform.SENSOR),
            async_add_sensor,
        )
    )

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            BT_MESH_DISCOVERY_ENTITY_NEW.format(BtMeshModelId.get_name(BtMeshModelId.GenericBatteryServer)),
            async_add_generic_battery,
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

    def __init__(self, app: BtMeshApplication, cfg_model: MeshCfgModel) -> None:
        if cfg_model.model_id != BtMeshModelId.GenericBatteryServer:
            raise ValueError("cfg_model.model_id must be GenericBatteryServer")

        BtMeshEntity.__init__(self, app, cfg_model)
        self._attr_available = False

    async def async_update(self) -> None:
        """Fetch new state data for the sensor."""
        result = await self.app.generic_battery_get(
            self.cfg_model.unicast_addr,
            self.cfg_model.app_key
        )
        self._attr_native_value = result.battery_level \
            if result is not None else None
        self._attr_available = self._attr_native_value is not None



# BT Mesh Sensor Server
class BtMeshSensorEntity(BtMeshEntity, SensorEntity):
    """Base class for Bluetooth Mesh sensor entity."""

    property_id: PropertyID
    update_period: int
    argument_keys: list
    argument_round = 2


    def __init__(
        self,
        app: BtMeshApplication,
        cfg_model: MeshCfgModel,
        update_period: int
    ) -> None:
        if cfg_model.model_id != BtMeshModelId.SensorServer:
            raise ValueError("cfg_model.model_id must be SensorServer")

        BtMeshEntity.__init__(self, app, cfg_model)
        self.update_period = update_period

        # update sensor unique_id and name attributes
        self._attr_unique_id = f"{self.cfg_model.unicast_addr:04x}-{self.cfg_model.model_id:04x}-{self.property_id}-{str(self.cfg_model.device.uuid)}"
        self._attr_name = f"{self.cfg_model.unicast_addr:04x}-{BtMeshModelId.get_name(self.cfg_model.model_id)}-{BtSensorAttrPropertyId.get_name(self.property_id)}"

        self._attr_available = False

#        _LOGGER.debug(self._attr_unique_id)
#        _LOGGER.debug(self._attr_name)


    async def _sensor_get(self):
        """Get sensor value."""
#        _LOGGER.debug("BtMeshSensor: _sensor_get()")
        return await self.app.sensor_get(
            self.cfg_model.unicast_addr,
            self.cfg_model.app_key,
            self.property_id
        )

    async def sensor_get(self):
        """Extract sensor value from response."""
        try:
            prop = await self._sensor_get()
            for key in self.argument_keys:
                prop = prop[key]
#            _LOGGER.debug(f"BtMeshSensor: prop={prop}")
            return round(float(prop), self.argument_round)
        except Exception as e:
            _LOGGER.debug(f"BtMeshSensor: _sensor_get(): {e}")
            return None

    async def async_update(self) -> None:
        """Fetch new state data for the sensor."""
#        _LOGGER.debug("BtMeshSensor: async_update()")
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


class ClassNotFoundError(Exception):
    """Factory could not find the class."""


class BtMeshSensorEntityFactory(object):
    @staticmethod
    def get(property_id: int) -> object:
        if type(property_id) != int:
            raise ValueError("property_id must be int")

        raw_subclasses_ = BtMeshSensorEntity.__subclasses__()
        print(raw_subclasses_)
        for subclass_ in raw_subclasses_:
            print(subclass_.property_id)
        classes: dict[int, Callable[..., object]] = {c.property_id:c for c in raw_subclasses_}
        class_ = classes.get(property_id, None)
        if class_ is not None:
            return class_

        raise ClassNotFoundError
