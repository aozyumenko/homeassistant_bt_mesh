"""BT Mesh Thermostat."""
from __future__ import annotations

import asyncio

from homeassistant.components.climate import PLATFORM_SCHEMA, ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    PRECISION_TENTHS,
    UnitOfTemperature,
)

from .bt_mesh.entity import BtMeshEntity
from .const import DOMAIN, BT_MESH_APPLICATION, BT_MESH_CFGCLIENT_CONF
from .bt_mesh import BtMeshModelId
from .mesh_cfgclient_conf import ELEMENT_MAIN


import logging
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    add_entities: AddEntitiesCallback,
) -> None:
    """Set up BT Mesh Climate entry."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    application = entry_data[BT_MESH_APPLICATION]
    mesh_cfgclient_conf = entry_data[BT_MESH_CFGCLIENT_CONF]

    entities = []
    devices = mesh_cfgclient_conf.devices

    for device in devices:
        try:
            device_unicat_addr = device['unicastAddress']

            # BT Mesh Thermostat Server
            for thermostat in device['models'][BtMeshModelId.ThermostatServer]:
                element_idx = thermostat[ELEMENT_MAIN]
                element_unicast_addr = device_unicat_addr + element_idx
                app_key = device['app_keys'][element_idx][BtMeshModelId.ThermostatServer]
                entities.append(
                     BtMeshClimate_Thermostat(
                        application=application,
                        uuid=device['UUID'],
                        cid=device['cid'],
                        pid=device['pid'],
                        vid=device['vid'],
                        addr=element_unicast_addr,
                        model_id=BtMeshModelId.ThermostatServer,
                        app_index=app_key
                    )
                )
        except KeyError:
            continue

    add_entities(entities)

    application.thermostat_init_receive_status()

    return True


class BtMeshClimate_Thermostat(BtMeshEntity, ClimateEntity):
    """Representation of an Bluetooth Mesh Vendor Thermostat."""

    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )
    _attr_target_temperature_step = 1.0
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    _state = None
    _range = None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._state is not None and self._range is not None

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        if self._state is not None:
            return self._state.present_temperature
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        if self._state is not None:
            return self._state.target_temperature
        return None

    @property
    def min_temp(self) -> float:
        """Return the lowbound target temperature we try to reach."""
        if self._range is None:
            return 40
        return self._range.min_temperature

    @property
    def max_temp(self) -> float:
        """Return the highbound target temperature we try to reach."""
        if self._range is None:
            return 0
        return self._range.max_temperature

    @property
    def hvac_action(self) -> HVACAction:
        """Return the current state of the thermostat."""
        if self._state is None:
            return HVACAction.OFF

        onoff_status = self._state['onoff_status']
        heater_status = self._state['heater_status']
        if not onoff_status:
            return HVACAction.OFF
        if heater_status:
            return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current state of the thermostat."""

        if self._state is None:
            return HVACMode.OFF

        onoff_status = self._state['onoff_status']
        if not onoff_status:
            return HVACMode.OFF
        return HVACMode.HEAT

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if self._state is None:
            return

        onoff_status = self._state.onoff_status
        temperature = self._state['target_temperature']

        if hvac_mode == HVACMode.OFF:
            onoff_status = False
        elif hvac_mode == HVACMode.HEAT:
            onoff_status = True

        await self.application.thermostat_set(
                self.unicast_addr,
                self.app_index,
                onoff_status,
                temperature
            )

    async def async_turn_off(self) -> None:
        """Turn thermostat off."""
        if self._state is None:
            return

        temperature = self._state.target_temperature
        await self.application.thermostat_set(
            self.unicast_addr,
            self.app_index,
            False,
            temperature
        )

    async def async_turn_on(self) -> None:
        """Turn thermostat on."""
        if self._state is None:
            return

        temperature = self._state.target_temperature
        await self.application.thermostat_set(
            self.unicast_addr,
            self.app_index,
            True,
            temperature
        )

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None or self._state is None:
            return

        onoff_status = self._state['onoff_status']
        await self.application.thermostat_set(
            self.unicast_addr,
            self.app_index,
            onoff_status,
            temperature
        )

    async def async_update(self):
        """Update the data from the thermostat."""
        self._range = await self.application.thermostat_range_get(
            self.unicast_addr,
            self.app_index
        )
        self._state = await self.application.thermostat_get(
            self.unicast_addr,
            self.app_index
        )
