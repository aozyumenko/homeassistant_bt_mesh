"""BT Mesh Thermostat."""
from __future__ import annotations

import asyncio

from construct import Container

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    HVACMode,
    ClimateEntityFeature,
    HVACAction,
    ATTR_HVAC_MODE,
)
from homeassistant.const import (
    Platform,
    ATTR_TEMPERATURE,
    UnitOfTemperature,
)

from bluetooth_mesh.models.vendor.thermostat import ThermostatClient
from bluetooth_mesh.messages.vendor.thermostat import (
    ThermostatOpcode,
    ThermostatSubOpcode,
    ThermostatMode,
    ThermostatStatusCode,
)

from bt_mesh_ctrl import BtMeshModelId

from .application import BtMeshApplication
from .entity import BtMeshEntity
from .const import (
    BT_MESH_DISCOVERY_ENTITY_NEW,
    BT_MESH_MSG,
    G_SEND_INTERVAL,
    G_TIMEOUT,
)

import logging
_LOGGER = logging.getLogger(__name__)



async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    add_entities: AddEntitiesCallback,
) -> None:
    """Set up BT Mesh Climate entity."""

    @callback
    def async_add_climate(
        app: BtMeshApplication,
        cfg_model: MeshCfgModel,
        passive: bool
    ) -> None:
#        _LOGGER.debug(f"async_add_climate(): uuid={cfg_model.device.uuid}, model_id={cfg_model.model_id}, addr={cfg_model.unicast_addr:04x}, app_key={cfg_model.app_key}")
        add_entities([BtMeshClimate_Thermostat(app, cfg_model, passive)])

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            BT_MESH_DISCOVERY_ENTITY_NEW.format(Platform.CLIMATE),
            async_add_climate,
        )
    )

    return True


class BtMeshClimate_Thermostat(BtMeshEntity, ClimateEntity):
    """Representation of an Bluetooth Mesh Vendor Thermostat."""

    status_opcodes = (
        ThermostatOpcode.VENDOR_THERMOSTAT,
    )

    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )
    _attr_target_temperature_step = 1.0
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    _flag_update_range = True


    def __init__(
        self,
        app: BtMeshApplication,
        cfg_model: MeshCfgModel,
        passive: bool
    ) -> None:
        if cfg_model.model_id != BtMeshModelId.ThermostatServer:
            raise ValueError("cfg_model.model_id must be ThermostatServer")

        BtMeshEntity.__init__(self, app, cfg_model, passive)
        self._attr_available = False

    def receive_message(
        self,
        source: int,
        app_index: int,
        destination: Union[int, UUID],
        message: ParsedMeshMessage
    ):
        """Receive status reports from Vendor Thermostat model."""
        vendor_message = message['vendor_thermostat']
        match vendor_message.subopcode:
            case ThermostatSubOpcode.THERMOSTAT_STATUS:
                if vendor_message.thermostat_status.status_code == ThermostatStatusCode.GOOD:
                    #self.update_model_state_thr(vendor_message.thermostat_status)
                    self.update_model_state(vendor_message.thermostat_status)
            case ThermostatSubOpcode.THERMOSTAT_RANGE_STATUS:
                self._attr_min_temp = vendor_message.thermostat_range_status.min_temperature
                self._attr_max_temp = vendor_message.thermostat_range_status.max_temperature
            case _:
                pass


    async def query_model_state(self) -> any:
        """Query Vendor Thermostat state."""
        if self._flag_update_range:
            result = await self.app.thermostat_range_get(
                destination=self.unicast_addr,
                app_index=self.app_key,
            )
            if result is not None:
                self._attr_min_temp = result.min_temperature
                self._attr_max_temp = result.max_temperature
                self._flag_update_range = False

        return await self.app.thermostat_get(
            destination=self.unicast_addr,
            app_index=self.app_key,
        )

    async def thermostat_set(self, onoff: int, temperature: float) -> any:
        if self.model_state is None:
            return

        result = await self.app.thermostat_set(
            destination=self.unicast_addr,
            app_index=self.app_key,
            onoff=onoff,
            temperature=temperature
        )
        if result is not None:
            self.update_model_state(result)
        else:
            self.update_model_state(
                Container(
                    status_code=self.model_state.status_code,
                    heater_status=self.model_state.heater_status,
                    mode=self.model_state.mode,
                    onoff_status=onoff,
                    target_temperature=temperature,
                    present_temperature=self.model_state.present_temperature
                )
            )

    async def async_update(self):
        """Update the data from the thermostat."""

        if self.model_state is not None:
            self._attr_current_temperature = self.model_state.present_temperature
            self._attr_target_temperature = self.model_state.target_temperature
            if self.model_state.onoff_status:
                if self.model_state.heater_status:
                    self._attr_hvac_action = HVACAction.HEATING
                else:
                    self._attr_hvac_action = HVACAction.IDLE
                self._attr_hvac_mode = HVACMode.HEAT
            else:
                self._attr_hvac_action = HVACAction.OFF
                self._attr_hvac_mode = HVACMode.OFF
            self._attr_available = hasattr(self, "_attr_min_temp") and \
                hasattr(self, "_attr_max_temp")
        else:
            self._attr_current_temperature = None
            self._attr_target_temperature = None
            self._attr_hvac_action = None
            self._attr_hvac_mode = None
            self._attr_available = False


    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target operation mode."""
        if self.model_state:
            match hvac_mode:
                case HVACMode.HEAT:
                    onoff = 1
                case HVACMode.OFF:
                    onoff = 0
                case _:
                    onoff = 0

            await self.thermostat_set(
                onoff=onoff,
                temperature=self.model_state.target_temperature
            )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature (and operation mode if set)."""
        if self.model_state and \
                (ATTR_HVAC_MODE in kwargs or ATTR_TEMPERATURE in kwargs):

            if ATTR_HVAC_MODE in kwargs:
                match kwargs[ATTR_HVAC_MODE]:
                    case HVACMode.HEAT:
                        onoff = 1
                    case HVACMode.OFF:
                        onoff = 0
                    case _:
                        onoff = self.model_state.onoff_status
            else:
                onoff = self.model_state.onoff_status


            if ATTR_TEMPERATURE in kwargs:
                temperature = kwargs[ATTR_TEMPERATURE]
            else:
                temperature = self.model_state.target_temperature

            await self.thermostat_set(
                onoff=onoff,
                temperature=temperature
            )
