"""BT MESH light"""
from __future__ import annotations

import math
import asyncio
from construct import Container

from bluetooth_mesh.messages.light.lightness import LightLightnessOpcode
from bluetooth_mesh.messages.light.ctl import LightCTLOpcode
from bluetooth_mesh.messages.light.hsl import LightHSLOpcode

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.components import light
from homeassistant.components.light import (
    ATTR_TRANSITION,
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    DEFAULT_MIN_KELVIN,
    DEFAULT_MAX_KELVIN,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.const import Platform

from .bt_mesh.entity import BtMeshEntity, ClassNotFoundError
from .bt_mesh import BtMeshModelId
from .bt_mesh.mesh_cfgclient_conf import MeshCfgModel
from .const import DOMAIN, BT_MESH_APPLICATION, BT_MESH_DISCOVERY_ENTITY_NEW

import logging
_LOGGER = logging.getLogger(__name__)



async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    add_entities: AddEntitiesCallback,
) -> None:
    """Set up BT Mesh light entry."""

    # FIXME: drop?
    app = hass.data[DOMAIN][config_entry.entry_id][BT_MESH_APPLICATION]

    @callback
    def async_add_light(
        app: BtMeshApplication,
        cfg_model: MeshCfgModel,
        passive: bool
    ) -> None:
#        _LOGGER.debug(f"async_add_light(): uuid={cfg_model.device.uuid}, model_id={cfg_model.model_id}, addr={cfg_model.unicast_addr:04x}, app_key={cfg_model.app_key}")
        try:
            add_entities([BtMeshLightEntityFactory.get(cfg_model.model_id)(app, cfg_model, passive)])
        except ClassNotFoundError as e:
            _LOGGER.error(f"failed to get BtMeshLightEntity object for model {BtMeshModelId.get_name(cfg_model.model_id)}")
            pass

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            BT_MESH_DISCOVERY_ENTITY_NEW.format(Platform.LIGHT),
            async_add_light,
        )
    )

    return True


class BtMeshLightEntity(BtMeshEntity, LightEntity):
    """Common representation of a BT Mesh Light entity."""

    model_id: int

    @staticmethod
    def brightness_hass_to_btmesh(val: int) -> int:
        return val * 256 if val < 255 else 65535

    @staticmethod
    def brightness_btmesh_to_hass(val: int) -> int:
        return int(val / 256)

    @staticmethod
    def color_hass_to_btmesh(color: tuple[float, float]) -> (int, int):
        hue = math.ceil(color[0] * 65535.0 / 360.0)
        saturation = math.ceil(color[1] * 65535.0 / 100.0)
        return (hue, saturation)

    @staticmethod
    def color_btmesh_to_hass(hue: int, saturation: int) -> tuple[float, float]:
        return [
            math.ceil(hue * 360.0 / 65535.0),
            math.ceil(saturation * 100.0 / 65535.0)
        ]


class BtMeshLight_LightLightness(BtMeshLightEntity):
    """Representation of a BT Mesh LightLightness."""

    model_id = BtMeshModelId.LightLightnessServer

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_supported_features = LightEntityFeature.TRANSITION

    _attr_available = False
    _last_state: int | None = None

    async def async_update(self) -> None:
        state = await self.app.light_lightness_get(
            self.cfg_model.unicast_addr,
            self.cfg_model.app_key,
        )
        if state is not None:
            if "remaining_time" in state and state.remaining_time > 0:
                lightness = state.target_lightness
            else:
                lightness = state.present_lightness
            self._attr_brightness = BtMeshLightEntity.brightness_btmesh_to_hass(lightness)
            self._attr_is_on = self._attr_brightness > 0
            self._attr_available = True

            if lightness > 0:
                self._last_state = lightness
        else:
            self._attr_available = False


    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""

        transition_time = int(kwargs[ATTR_TRANSITION]) if ATTR_TRANSITION in kwargs else None
#        _LOGGER.debug(f"async_turn_on(): transition_time = {transition_time}")

        if ATTR_BRIGHTNESS in kwargs:
            await self.app.light_lightness_set(
                self.cfg_model.unicast_addr,
                self.cfg_model.app_key,
                BtMeshLightEntity.brightness_hass_to_btmesh(kwargs[ATTR_BRIGHTNESS]),
                transition_time=transition_time
            )
        else:
            await self.app.generic_onoff_set(
                self.cfg_model.unicast_addr,
                self.cfg_model.app_key,
                1,
                transition_time=transition_time
            )

            # hack that allows you to use GenericOnOff instead of
            # LightLighting to turn on the light
            if self._last_state:
                self.app.cache.update_and_invalidate(
                    self.cfg_model.unicast_addr,
                    LightLightnessOpcode.LIGHT_LIGHTNESS_STATUS,
                    Container(present_lightness=self._last_state)
                )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""

        transition_time = int(kwargs[ATTR_TRANSITION]) if ATTR_TRANSITION in kwargs else None
#        _LOGGER.debug(f"async_turn_off(): transition_time = {transition_time}")

        await self.app.light_lightness_set(
            self.cfg_model.unicast_addr,
            self.cfg_model.app_key,
            0,
            transition_time=transition_time
        )


class BtMeshLight_LightCTL(BtMeshLightEntity):
    """Representation of a BT Mesh LightCTL."""

    model_id = BtMeshModelId.LightCTLServer

    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP}
    _attr_supported_features = LightEntityFeature.TRANSITION

    _attr_available = False
    _attr_min_color_temp_kelvin = DEFAULT_MIN_KELVIN
    _attr_max_color_temp_kelvin = DEFAULT_MAX_KELVIN

    _last_state: tuple[int, int] | None = None
    _flag_update_temperature_range = True

    async def async_update(self) -> None:
        state = await self.app.light_ctl_get(
            self.cfg_model.unicast_addr,
            self.cfg_model.app_key
        )
        if state is not None:
#            _LOGGER.debug(f"CTL async_update(): state={state}")
            if "remaining_time" in state and state.remaining_time > 0:
                lightness = state.target_ctl_lightness
                temperature = state.target_ctl_temperature
            else:
                lightness = state.present_ctl_lightness
                temperature = state.present_ctl_temperature
            self._attr_brightness = BtMeshLightEntity.brightness_btmesh_to_hass(lightness)
            self._attr_color_temp_kelvin = temperature
            self._attr_is_on = self._attr_brightness > 0
            self._attr_available = True

            if lightness > 0:
                self._last_state = [lightness, temperature]
        else:
            self._attr_available = False

        if self._flag_update_temperature_range:
            state = await self.app.light_ctl_temperature_range_get(
                self.cfg_model.unicast_addr,
                self.cfg_model.app_key
            )
            if state is not None:
                self._attr_min_color_temp_kelvin = state.range_min
                self._attr_max_color_temp_kelvin = state.range_max
                self._flag_update_temperature_range = False

    async def async_turn_on(self, **kwargs):
        """Turn the specified light on."""

        transition_time = int(kwargs[ATTR_TRANSITION]) if ATTR_TRANSITION in kwargs else None
#        _LOGGER.debug(f"async_turn_on(): transition_time = {transition_time}")

        if ATTR_BRIGHTNESS in kwargs or ATTR_COLOR_TEMP_KELVIN in kwargs:
            arg_brightness = kwargs.get(ATTR_BRIGHTNESS, self._attr_brightness)
            arg_color_temp_kelvin = kwargs.get(ATTR_COLOR_TEMP_KELVIN, self._attr_color_temp_kelvin)

            if arg_brightness is not None and arg_color_temp_kelvin is not None:
                lightness = BtMeshLightEntity.brightness_hass_to_btmesh(arg_brightness)
                temperature = arg_color_temp_kelvin

                await self.app.light_ctl_set(
                    self.cfg_model.unicast_addr,
                    self.cfg_model.app_key,
                    lightness,
                    temperature,
                    transition_time=transition_time
                )
        else:
            await self.app.generic_onoff_set(
                self.cfg_model.unicast_addr,
                self.cfg_model.app_key,
                1,
                transition_time=transition_time
            )

            # hack that allows you to use GenericOnOff instead of
            # LightCTL to turn on the light
            if self._last_state:
                self.app.cache.update_and_invalidate(
                    self.cfg_model.unicast_addr,
                    LightCTLOpcode.LIGHT_CTL_STATUS,
                    Container(
                        present_ctl_lightness=self._last_state[0],
                        present_ctl_temperature=self._last_state[1],
                    )
                )
        self._flag_update_temperature_range = True


    async def async_turn_off(self, **kwargs):
        """Turn the specified light off."""

        transition_time = int(kwargs[ATTR_TRANSITION]) if ATTR_TRANSITION in kwargs else None
#        _LOGGER.debug(f"async_turn_on(): transition_time = {transition_time}")

        await self.app.generic_onoff_set(
            self.cfg_model.unicast_addr,
            self.cfg_model.app_key,
            0,
            transition_time=transition_time
        )

        # hack that allows you to use GenericOnOff instead of
        # LightCTL to turn on the light
        if self._last_state:
            self.app.cache.update_and_invalidate(
                self.cfg_model.unicast_addr,
                LightCTLOpcode.LIGHT_CTL_STATUS,
                Container(
                    present_ctl_lightness=0,
                    present_ctl_temperature=self._last_state[1],
                )
            )
        self._flag_update_temperature_range = True



class BtMeshLight_LightHSL(BtMeshLightEntity):
    """Representation of a BT Mesh LightHSL."""

    model_id = BtMeshModelId.LightHSLServer

    _attr_color_mode = ColorMode.HS
    _attr_supported_color_modes = {ColorMode.HS}
    _attr_supported_features = LightEntityFeature.TRANSITION

    _attr_available = False

    _last_state: tuple[int, int, int] | None = None

    async def async_update(self) -> None:
        state = await self.app.light_hsl_get_target(
            self.cfg_model.unicast_addr,
            self.cfg_model.app_key,
        )
        if state is not None:
            self._attr_brightness = BtMeshLightEntity.brightness_btmesh_to_hass(state.hsl_lightness)
            self._attr_hs_color = BtMeshLightEntity.color_btmesh_to_hass(state.hsl_hue, state.hsl_saturation)
            self._attr_is_on = self._attr_brightness > 0
            self._attr_available = True

            if state.hsl_lightness > 0:
                self._last_state = [state.hsl_lightness, state.hsl_hue, state.hsl_saturation]
        else:
            self._attr_available = False


    async def async_turn_on(self, **kwargs):
        """Turn the specified light on."""

        transition_time = int(kwargs[ATTR_TRANSITION]) if ATTR_TRANSITION in kwargs else None
#        _LOGGER.debug(f"async_turn_on(): transition_time = {transition_time}")

        if ATTR_BRIGHTNESS in kwargs or ATTR_HS_COLOR in kwargs:
            arg_brightness = kwargs.get(ATTR_BRIGHTNESS, self._attr_brightness)
            arg_color = kwargs.get(ATTR_HS_COLOR, self._attr_hs_color)

            if arg_brightness is not None and arg_color is not None:
                lightness = BtMeshLightEntity.brightness_hass_to_btmesh(arg_brightness)
                (hue, saturation) = BtMeshLightEntity.color_hass_to_btmesh(arg_color)

                await self.app.light_hsl_set(
                    self.cfg_model.unicast_addr,
                    self.cfg_model.app_key,
                    lightness,
                    hue,
                    saturation,
                    transition_time=transition_time
                )
        else:
            await self.app.generic_onoff_set(
                self.cfg_model.unicast_addr,
                self.cfg_model.app_key,
                1,
                transition_time=transition_time
            )

            # hack that allows you to use GenericOnOff instead of
            # LightHSL to turn off the light
            if self._last_state:
                self.app.cache.update_and_invalidate(
                    self.cfg_model.unicast_addr,
                    LightHSLOpcode.LIGHT_HSL_TARGET_STATUS,
                    Container(
                        hsl_lightness=self._last_state[0],
                        hsl_hue=self._last_state[1],
                        hsl_saturation=self._last_state[2]
                    )
                )

    async def async_turn_off(self, **kwargs):
        """Turn the specified light off."""

        transition_time = int(kwargs[ATTR_TRANSITION]) if ATTR_TRANSITION in kwargs else None
#        _LOGGER.debug(f"async_turn_on(): transition_time = {transition_time}")

        await self.app.generic_onoff_set(
            self.cfg_model.unicast_addr,
            self.cfg_model.app_key,
            0,
            transition_time=transition_time
        )

        # hack that allows you to use GenericOnOff instead of
        # LightHSL to turn off the light
        if self._last_state:
            self.app.cache.update_and_invalidate(
                self.cfg_model.unicast_addr,
                LightHSLOpcode.LIGHT_HSL_TARGET_STATUS,
                Container(
                    hsl_lightness=0,
                    hsl_hue=self._last_state[1],
                    hsl_saturation=self._last_state[2]
                )
            )


class BtMeshLightEntityFactory(object):
    @staticmethod
    def get(model_id: int) -> object:
        if type(model_id) != BtMeshModelId:
            raise ValueError("model_id must be int")

        raw_subclasses_ = BtMeshLightEntity.__subclasses__()
        classes: dict[int, Callable[..., object]] = {c.model_id:c for c in raw_subclasses_}
        class_ = classes.get(model_id, None)
        if class_ is not None:
            return class_

        raise ClassNotFoundError
