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
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.dispatcher import async_dispatcher_connect

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

#    entry_data = hass.data[DOMAIN][config_entry.entry_id]
#    app = entry_data[BT_MESH_APPLICATION]

    @callback
    def async_add_sensor(
        app: BtMeshApplication,
        cfg_model: MeshCfgModel,
        property_id: PropertyID,
        update_period: int
    ) -> None:
        _LOGGER.debug("async_add_sensor(): uuid=%s, addr=0x%04x, app_key=%d, property_id=0x%x, update_period=%d" % (cfg_model.device.uuid, cfg_model.unicast_addr, cfg_model.app_key, property_id, update_period))
        try:
            sensor_entity = BtMeshSensorEntityFactory.get(property_id)(
                app,
                cfg_model,
                update_period
            )
            async_add_entities([sensor_entity])
            _LOGGER.debug(f"sensor_entity = {sensor_entity}")
        except Exception as e:
            _LOGGER.debug(f"failed to create BtMeshSensorEntity: {e}")
            pass


    @callback
    def async_add_battery(info) -> None:
        _LOGGER.debug("async_add_sensor()")

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            BT_MESH_DISCOVERY_ENTITY_NEW.format("sensor"),
            async_add_sensor,
        )
    )

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            BT_MESH_DISCOVERY_ENTITY_NEW.format("battery"),
            async_add_battery,
        )
    )


#    entry_data = hass.data[DOMAIN][config_entry.entry_id]
#    application = entry_data[BT_MESH_APPLICATION]
#    mesh_cfgclient_conf = entry_data[BT_MESH_CFGCLIENT_CONF]

#                                sensor = create_sensor(
#                                    application=application,
#                                    uuid=device['UUID'],
#                                    cid=int(device['cid']),
#                                    pid=int(device['pid']),
#                                    vid=int(device['vid']),
#                                    addr=element_unicast_addr,
#                                    app_index=app_index,
#                                    property_id=property_id
#                                )

#                                if sensor != None:
#                                    entities.append(sensor)


            # listing Generic Battery model
#            if BtMeshModelId.GenericBatteryServer in device['models']:
#                _LOGGER.debug(device['models'][BtMeshModelId.GenericBatteryServer])
#                for generic_battery in device['models'][BtMeshModelId.GenericBatteryServer]:
#                    element_idx = generic_battery[PATTERN_MAIN]
#                    element_unicast_addr = device_unicat_addr + element_idx
#                    app_index = device['app_keys'][element_idx][BtMeshModelId.GenericBatteryServer]
#                    _LOGGER.debug("GenericBatteryServer: uuid=%s, %d, addr=0x%04x, app_key=%d" % (device['UUID'], element_idx, element_unicast_addr, app_index))

#                    sensor = BtMeshGenericBatteryEntity(
#                        application=application,
#                        uuid=device['UUID'],
#                        cid=int(device['cid']),
#                        pid=int(device['pid']),
#                        vid=int(device['vid']),
#                        addr=element_unicast_addr,
#                        app_index=app_index
#                    )
#                    entities.append(sensor)

#        except KeyError:
#            continue

#    add_entities(entities)

#    application.sensor_init_receive_status()
#    application.generic_battery_init_receive_status()

    return True






# BT Mesh Generic Battery Server

#class BtMeshGenericBatteryEntity(BtMeshEntity, SensorEntity):
#    """Class for Bluetooth Mesh Generic Battery sensor."""

#    def __init__(
#        self,
#        application,
#        uuid,
#        cid,
#        pid,
#        vid,
#        addr,
#        app_index
#    ) -> None:
#        BtMeshEntity.__init__(
#            self,
#            application,
#            uuid,
#            cid,
#            pid,
#            vid,
#            addr,
#            BtMeshModelId.GenericBatteryServer,
#            app_index,
#        )
#        self.entity_description = SensorEntityDescription(
#            key="battery_level",
#            device_class=SensorDeviceClass.BATTERY,
#            native_unit_of_measurement=PERCENTAGE,
#            state_class=SensorStateClass.MEASUREMENT,
#            entity_category=EntityCategory.DIAGNOSTIC,
#            name="Battery Level",
#        )

#    async def async_update(self) -> None:
#        """Fetch new state data for the sensor."""
#        result = await self.application.generic_battery_get(
#            self.unicast_addr,
#            self.app_index
#        )
#        if result is not None:
#            self._attr_native_value = result.battery_level



# BT Mesh Sensor Server


class BtMeshSensorEntity(BtMeshEntity, SensorEntity):
    """Base class for Bluetooth Mesh sensor entity."""

    property_id: PropertyID
    entity_description: SensorEntityDescription

    update_period: int

    def __init__(
        self,
        app: BtMeshApplication,
        cfg_model: MeshCfgModel,
        update_period: int
    ) -> None:
        BtMeshEntity.__init__(self, app, cfg_model)
        self.update_period = update_period

        # update sensor unique_id and name attributes
        self._attr_unique_id = f"{self.cfg_model.unicast_addr:04x}-{self.cfg_model.model_id:04x}-{self.property_id}-{str(self.cfg_model.device.uuid)}"
        self._attr_name = f"{self.cfg_model.unicast_addr:04x}-{BtMeshModelId.get_name(self.cfg_model.model_id)}-{BtSensorAttrPropertyId.get_name(self.property_id)}"

        _LOGGER.debug(self._attr_unique_id)
        _LOGGER.debug(self._attr_name)


    async def sensor_get(self):
        """Get sensor value."""
        _LOGGER.debug("BtMeshSensor: sensor_get()")
        return await self.app.sensor_get(
            self.cfg_model.unicast_addr,
            self.cfg_model.app_key,
            self.property_id
        )

    async def async_update(self) -> None:
        """Fetch new state data for the sensor."""
        _LOGGER.debug("BtMeshSensor: async_update()")
        self._attr_native_value = await self.sensor_get()


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

    def __init__(
        self,
        app: BtMeshApplication,
        cfg_model: MeshCfgModel,
        update_period: int
    ) -> None:
        super().__init__(
            app,
            cfg_model,
            update_period,
        )

    async def sensor_get(self):
        """Get power value."""
        _LOGGER.debug("BtMeshSensor_PresentDeviceInputPower: sensor_get()")
        try:
            property = await super().sensor_get()
            return round(float(property['present_device_input_power']['power']), 2)
        except Exception as e:
            _LOGGER.debug(e)
            return None


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

    def __init__(
        self,
        app: BtMeshApplication,
        cfg_model: MeshCfgModel,
        update_period: int
    ) -> None:
        super().__init__(
            app,
            cfg_model,
            update_period,
        )

    async def sensor_get(self):
        """Get power value."""
        try:
            property = await super().sensor_get()
            return round(float(property['present_input_current']['current']), 3)
        except Exception as e:
            _LOGGER.debug(e)
            return None


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

    def __init__(
        self,
        app: BtMeshApplication,
        cfg_model: MeshCfgModel,
        update_period: int
    ) -> None:
        super().__init__(app, cfg_model, update_period)

    async def sensor_get(self):
        """Get enegry value."""
        try:
            property = await super().sensor_get()
            return float(property['precise_total_device_energy_use']['energy'])
        except Exception as e:
            _LOGGER.debug(e)
            return None


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

    def __init__(
        self,
        app: BtMeshApplication,
        cfg_model: MeshCfgModel,
        update_period: int
    ) -> None:
        super().__init__(
            app,
            cfg_model,
            update_period,
        )

    async def sensor_get(self):
        """Get voltage value."""
        try:
            property = await super().sensor_get()
            return round(float(property['present_input_voltage']['voltage']), 2)
        except Exception as e:
            _LOGGER.debug(e)
            return None


class ClassNotFoundError(Exception):
    """Factory could not find the class."""


class BtMeshSensorEntityFactory(object):
    @staticmethod
    def get(property_id: int) -> object:
        if type(property_id) != int:
            raise ValueError("property_id must be a int")

        raw_subclasses_ = BtMeshSensorEntity.__subclasses__()
        print(raw_subclasses_)
        for subclass_ in raw_subclasses_:
            print(subclass_.property_id)
        classes: dict[int, Callable[..., object]] = {c.property_id:c for c in raw_subclasses_}
        class_ = classes.get(property_id, None)
        if class_ is not None:
            return class_

        raise ClassNotFoundError
