"""BT MESH sensor integration"""
from __future__ import annotations

import asyncio
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
    SensorEntityDescription,
)
from homeassistant.const import (
    ENERGY_KILO_WATT_HOUR,
    ELECTRIC_POTENTIAL_VOLT,
    ELECTRIC_CURRENT_AMPERE,
    POWER_WATT
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
#, DeviceInfo
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from bluetooth_mesh.messages.properties import PropertyID

from . import BtMeshEntity
from .const import DOMAIN, BT_MESH_APPLICATION, BT_MESH_CFGCLIENT_CONF
from .bt_mesh import BtMeshModelId, BtSensorAttrPropertyId
from .mesh_cfgclient_conf import ELEMENT_MAIN


_LOGGER = logging.getLogger(__name__)



SENSOR_TYPES = {
    PropertyID.PRECISE_TOTAL_DEVICE_ENERGY_USE: SensorEntityDescription(
        key="totalenergy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        name="Total Energy",
    ),
}



async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigType,
    add_entities: AddEntitiesCallback
) -> None:
    """Set up the BT MESH sensor entry."""

    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    application = entry_data[BT_MESH_APPLICATION]
    mesh_cfgclient_conf = hass.data[DOMAIN][BT_MESH_CFGCLIENT_CONF]

    _LOGGER.debug("async_setup_entry(): config_entry: %s, entry_data=%s, application=%s" % (config_entry.data, entry_data, application))
    _LOGGER.debug("async_setup_entry(): devices=%s" % (mesh_cfgclient_conf.devices))

    entities = []
    devices = mesh_cfgclient_conf.devices
    for device in devices:
        try:
            device_unicat_addr = device['unicastAddress']
            for sensor in device['models'][BtMeshModelId.SensorServer]:
                element_idx = sensor[ELEMENT_MAIN]
                element_unicast_addr = device_unicat_addr + element_idx
                app_index = device['app_keys'][element_idx][BtMeshModelId.GenericOnOffServer]
                #_LOGGER.debug("uuid=%s, %d, addr=0x%04x, app_key=%d" % (device['UUID'], element_idx, element_unicast_addr, app_key))
                # TODO: get descriptor
                descriptor = await application.sensor_descriptor_get(element_unicast_addr, app_index);
                if hasattr(descriptor, "__iter__"):
                    for propery in descriptor:
                        if hasattr(propery, "sensor_property_id"):
                            property_id = int(propery['sensor_property_id'])
#                            _LOGGER.debug("uuid=%s, %d, addr=0x%04x, app_index=%d, property_id=0x%x" % (device['UUID'], element_idx, element_unicast_addr, app_index, property_id))

                            sensor = create_sensor(
                                application=application,
                                uuid=device['UUID'],
                                cid=int(device['cid']),
                                pid=int(device['pid']),
                                vid=int(device['vid']),
                                addr=element_unicast_addr,
                                app_index=app_index,
                                property_id=property_id
                            )

                            if sensor != None:
                                val = await sensor.sensor_get()
                                entities.append(sensor)

                        else:
                            # TODO: set aside the node for later processing
                            pass

        except KeyError:
            continue

    add_entities(entities)

    application.sensor_init_receive_status()

    return True



def create_sensor(
    application: BtMeshApplication,
    uuid: str,
    cid: int,
    pid: int,
    vid: int,
    addr: int,
    app_index: int,
    property_id: int
) -> BtMeshSensorEntity | None:
    _LOGGER.debug("uuid=%s, addr=0x%04x, app_index=%d, property_id=0x%x" % (uuid, addr, app_index, property_id))

    if property_id in SENSOR_CLASSES:
        return SENSOR_CLASSES[property_id](
            application=application,
            uuid=uuid,
            cid=cid,
            pid=pid,
            vid=vid,
            addr=addr,
            app_index=app_index
        )

    else:
        _LOGGER.debug("    NOT FOUND")
        return None


class BtMeshSensorEntity(BtMeshEntity, SensorEntity):
    """Base class for Bluetooth Mesh sensor."""

    _attr_property_id: int

    def __init__(
        self,
        application,
        uuid,
        cid,
        pid,
        vid,
        addr,
        app_index,
        property_id,
        entity_description: SensorEntityDescription
    ) -> None:
        BtMeshEntity.__init__(self, application, uuid, cid, pid, vid, addr, BtMeshModelId.SensorServer, app_index);
        self.entity_description = entity_description
        self._attr_property_id = property_id;

        # update sensor ID and Name
        self._attr_name = "%04x-%s-%s" % (
            self._unicast_addr,
            BtMeshModelId.get_name(self._model_id),
            BtSensorAttrPropertyId.get_name(self._attr_property_id)
        )
        self._attr_unique_id = "%04x-%04x-%04x" % (
            self._unicast_addr,
            self._model_id,
            self._attr_property_id
        )

    @property
    def property_id(self):
        """Return sensor Propery Id."""
        return self._attr_property_id


    async def sensor_get(self):
        """Get sensor value."""
        return await self.application.sensor_get(
            self.unicast_addr,
            self.app_index,
            self.property_id
        )



class BtMeshSensor_PresentDeviceInputPower(BtMeshSensorEntity):
    """..."""

    def __init__(self, application, uuid, cid, pid, vid, addr, app_index) -> None:
        super().__init__(
            application,
            uuid,
            cid,
            pid,
            vid,
            addr,
            app_index,
            PropertyID.PRESENT_DEVICE_INPUT_POWER,
            SensorEntityDescription(
                key="present_device_input_power",
                device_class=SensorDeviceClass.POWER,
                native_unit_of_measurement=POWER_WATT,
                state_class=SensorStateClass.MEASUREMENT,
                name="Power",
            )
        )

    async def sensor_get(self):
        """Get power value."""
        try:
            property = await super().sensor_get()
            return round(float(property['present_device_input_power']['power']), 2)
        except Exception:
            return None

    async def async_update(self) -> None:
        """Fetch new state data for the sensor."""
        self._attr_native_value = await self.sensor_get()


class BtMeshSensor_PresentInputCurrent(BtMeshSensorEntity):
    """..."""

    def __init__(self, application, uuid, cid, pid, vid, addr, app_index) -> None:
        super().__init__(
            application,
            uuid,
            cid,
            pid,
            vid,
            addr,
            app_index,
            PropertyID.PRESENT_INPUT_CURRENT,
            SensorEntityDescription(
                key="present_input_current",
                device_class=SensorDeviceClass.CURRENT,
                native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
                state_class=SensorStateClass.MEASUREMENT,
                name="Current",
            )
        )

    async def sensor_get(self):
        """Get power value."""
        try:
            property = await super().sensor_get()
            return round(float(property['present_input_current']['current']), 3)
        except Exception:
            return None

    async def async_update(self) -> None:
        """Fetch new state data for the sensor."""
        self._attr_native_value = await self.sensor_get()


class BtMeshSensor_PreciseTotalDeviceEnergyUse(BtMeshSensorEntity):
    """..."""

    def __init__(self, application, uuid, cid, pid, vid, addr, app_index) -> None:
        super().__init__(
            application,
            uuid,
            cid,
            pid,
            vid,
            addr,
            app_index,
            PropertyID.PRECISE_TOTAL_DEVICE_ENERGY_USE,
            SensorEntityDescription(
                key="totalenergy",
                device_class=SensorDeviceClass.ENERGY,
                native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
                state_class=SensorStateClass.TOTAL_INCREASING,
                name="Total Energy",
            )
        )

    async def sensor_get(self):
        """Get enegry value."""
        try:
            property = await super().sensor_get()
            return float(property['precise_total_device_energy_use']['energy'])
        except Exception:
            return None

    async def async_update(self) -> None:
        """Fetch new state data for the sensor."""
        self._attr_native_value = await self.sensor_get()



class BtMeshSensor_PresentInputVoltage(BtMeshSensorEntity):
    """..."""

    def __init__(self, application, uuid, cid, pid, vid, addr, app_index) -> None:
        super().__init__(
            application,
            uuid,
            cid,
            pid,
            vid,
            addr,
            app_index,
            PropertyID.PRESENT_INPUT_VOLTAGE,
            SensorEntityDescription(
                key="present_input_voltage",
                device_class=SensorDeviceClass.VOLTAGE,
                native_unit_of_measurement=ELECTRIC_POTENTIAL_VOLT,
                state_class=SensorStateClass.MEASUREMENT,
                name="Voltage",
            )
        )

    async def sensor_get(self):
        """Get voltage value."""
        try:
            property = await super().sensor_get()
            return round(float(property['present_input_voltage']['voltage']), 2)
        except Exception:
            return None

    async def async_update(self) -> None:
        """Fetch new state data for the sensor."""
        self._attr_native_value = await self.sensor_get()



SENSOR_CLASSES = {
    PropertyID.PRESENT_DEVICE_INPUT_POWER: BtMeshSensor_PresentDeviceInputPower,
    PropertyID.PRECISE_TOTAL_DEVICE_ENERGY_USE: BtMeshSensor_PreciseTotalDeviceEnergyUse,
    PropertyID.PRESENT_INPUT_VOLTAGE: BtMeshSensor_PresentInputVoltage,
    PropertyID.PRESENT_INPUT_CURRENT: BtMeshSensor_PresentInputCurrent
}
