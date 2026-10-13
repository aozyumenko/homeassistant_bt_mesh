"""BT MESH light"""
from __future__ import annotations

import math
from typing import Any, Callable, Union
from uuid import UUID

from construct import Container

from bluetooth_mesh.utils import ParsedMeshMessage
from bluetooth_mesh.messages.generic.onoff import GenericOnOffOpcode
from bluetooth_mesh.messages.light.lightness import LightLightnessOpcode
from bluetooth_mesh.messages.light.ctl import LightCTLOpcode
from bluetooth_mesh.messages.light.hsl import LightHSLOpcode

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
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

from bt_mesh_ctrl import BtMeshModelId, BtMeshOpcode
from bt_mesh_ctrl.mesh_cfgclient_conf import MeshCfgModel

from .application import BtMeshApplication
from .entity import BtMeshEntity, ClassNotFoundError
from .const import (
    BT_MESH_DISCOVERY_ENTITY_NEW,
    DEFAULT_LIGHT_BRIGHTNESS,
    DEFAULT_LIGHT_TEMPERATURE,

    G_MESH_CACHE_UPDATE_TIMEOUT,
    G_MESH_CACHE_INVALIDATE_TIMEOUT,
    CONF_UPDATE_TIME,
    CONF_KEEPALIVE_TIME,
)

import logging
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    add_entities: AddEntitiesCallback,
) -> None:
    """Set up BT Mesh light entry."""

    @callback
    def async_add_light(
        app: BtMeshApplication,
        cfg_model: MeshCfgModel,
        node_conf: dict
    ) -> None:
        platform_conf = node_conf.get(Platform.LIGHT, None) or {}
        update_timeout = platform_conf.get(
            CONF_UPDATE_TIME,
            node_conf.get(CONF_UPDATE_TIME, G_MESH_CACHE_UPDATE_TIMEOUT)
        )
        invalidate_timeout = platform_conf.get(
            CONF_KEEPALIVE_TIME,
            node_conf.get(CONF_KEEPALIVE_TIME, G_MESH_CACHE_INVALIDATE_TIMEOUT)
        )

        try:
            add_entities(
                [
                    BtMeshLightEntityFactory.get(cfg_model.model_id)(
                        app=app,
                        cfg_model=cfg_model,
                        update_timeout=update_timeout,
                        invalidate_timeout=invalidate_timeout
                    )
                ]
            )
        except ClassNotFoundError:
            _LOGGER.error(f"failed to get BtMeshLightEntity object for model {BtMeshModelId.get_name(cfg_model.model_id)}")

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            BT_MESH_DISCOVERY_ENTITY_NEW.format(BtMeshModelId.LightLightnessServer),
            async_add_light,
        )
    )
    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            BT_MESH_DISCOVERY_ENTITY_NEW.format(BtMeshModelId.LightCTLServer),
            async_add_light,
        )
    )
    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            BT_MESH_DISCOVERY_ENTITY_NEW.format(BtMeshModelId.LightHSLServer),
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

    @staticmethod
    def extract_generic_onoff_status(generic_onoff_status: Container) -> bool:
        if generic_onoff_status is not None:
            if "target_onoff" in generic_onoff_status and \
                    "remaining_time" in generic_onoff_status and \
                    generic_onoff_status.remaining_time > 0:
                return generic_onoff_status.target_onoff
            else:
                return generic_onoff_status.present_onoff
        else:
            return None

    @staticmethod
    def extract_light_lightness_status(
        light_lightness_status: Container
    ) -> int:
        try:
            if light_lightness_status is not None:
                if "target_onoff" in light_lightness_status and \
                        "remaining_time" in light_lightness_status and \
                        light_lightness_status.remaining_time > 0:
                    return light_lightness_status.target_lightness
                else:
                    return light_lightness_status.present_lightness
            else:
                return None
        except KeyError:
            # FIXME: debug only
            _LOGGER.error(f"key_error: {light_lightness_status}")
            return None

    @staticmethod
    def extract_light_ctl_status(
        light_ctl_status: Container
    ) -> tuple[int, int] | None:
        if light_ctl_status is not None:
            if "target_ctl_temperature" in light_ctl_status and \
                    "remaining_time" in light_ctl_status \
                    and light_ctl_status.remaining_time > 0:
                lightness = light_ctl_status.target_ctl_lightness
                temperature = light_ctl_status.target_ctl_temperature
            else:
                lightness = light_ctl_status.present_ctl_lightness
                temperature = light_ctl_status.present_ctl_temperature
            return [lightness, temperature]
        else:
            return None

    @staticmethod
    def extract_light_hsl_status(
        light_hsl_status: Container
    ) -> tuple[int, int, int] | None:
        if light_hsl_status is not None:
            return [
                light_hsl_status.hsl_lightness,
                light_hsl_status.hsl_hue,
                light_hsl_status.hsl_saturation
            ]
        else:
            return None


class BtMeshLight_LightLightness(BtMeshLightEntity):
    """Representation of a BT Mesh LightLightness."""

    status_opcodes = (
        GenericOnOffOpcode.GENERIC_ONOFF_STATUS,
        LightLightnessOpcode.LIGHT_LIGHTNESS_STATUS,
    )

    model_id = BtMeshModelId.LightLightnessServer

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_supported_features = LightEntityFeature.TRANSITION

    _attr_available = False
    _last_state: int | None = None

    def status_onoff_to_lightness(self, onoff_status: Container):
        """Convert GenericOnOff status to the LightLightness based on last state."""
        is_on = BtMeshLightEntity.extract_generic_onoff_status(onoff_status)
        if is_on is not None:
            if self._last_state is not None:
                present_lightness = self._last_state if is_on else 0
            else:
                present_lightness = (
                    self.brightness_hass_to_btmesh(DEFAULT_LIGHT_BRIGHTNESS)
                    if is_on
                    else 0
                )
            return Container(
                present_lightness=present_lightness
            )
        else:
            return None

    def update_entity_state(self, light_lightness_status: Container):
        """Extract light state from LightLightness status."""
        lightness = BtMeshLightEntity.extract_light_lightness_status(
            light_lightness_status
        )
        if lightness is not None:
            self._attr_brightness = BtMeshLightEntity.brightness_btmesh_to_hass(
                lightness
            )
            self._attr_is_on = self._attr_brightness > 0
            self._attr_available = True

            if lightness > 0:
                self._last_state = lightness
        else:
            self._attr_available = False

    def receive_message(
        self,
        source: int,
        app_index: int,
        destination: Union[int, UUID],
        message: ParsedMeshMessage
    ):
        """Receive status reports from LightCTL model."""
        match message.opcode:
            case GenericOnOffOpcode.GENERIC_ONOFF_STATUS:
                status = self.status_onoff_to_lightness(
                    message.generic_onoff_status
                )
                self.update_model_state(status)
                self.update_entity_state(status)
                self.async_write_ha_state()
            case LightLightnessOpcode.LIGHT_LIGHTNESS_STATUS:
                self.update_entity_state(message.light_lightness_status)
                self.async_write_ha_state()
                super().receive_message(source, app_index, destination, message)

    async def query_model_state(self) -> any:
        """Get LightLightness state."""
        return await self.app.light_lightness_get(
            destination=self.unicast_addr,
            app_index=self.app_key,
        )

    async def async_update(self) -> None:
        """Update LightEntity state from latest LightLightness."""
        self.update_entity_state(self.model_state)

    async def light_lightness_set(
        self,
        lightness: int,
        transition_time: float = None
    ) -> None:
        """Set LightLightness lightness."""
        result = await self.app.light_lightness_set(
            destination=self.unicast_addr,
            app_index=self.app_key,
            lightness=lightness,
            transition_time=transition_time,
        )
        if result is not None:
            self.update_model_state(result)
        else:
            self.update_model_state(Container(present_lightness=lightness))
        self.invalidate_device_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        transition_time = (
            int(kwargs[ATTR_TRANSITION])
            if ATTR_TRANSITION in kwargs
            else None
        )

        if ATTR_BRIGHTNESS in kwargs:
            await self.light_lightness_set(
                BtMeshLightEntity.brightness_hass_to_btmesh(kwargs[ATTR_BRIGHTNESS]),
                transition_time=transition_time
            )
        else:
            await self.app.generic_onoff_set(
                destination=self.unicast_addr,
                app_index=self.app_key,
                onoff=1,
                transition_time=transition_time
            )

            self.update_model_state(
                Container(
                    present_onoff=1
                )
            )
            self.invalidate_device_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        transition_time = (
            int(kwargs[ATTR_TRANSITION])
            if ATTR_TRANSITION in kwargs
            else None
        )
        await self.light_lightness_set(0, transition_time=transition_time)

        self.update_model_state(
            Container(
                present_onoff=0
            )
        )


class BtMeshLight_LightCTL(BtMeshLightEntity):
    """Representation of a BT Mesh LightCTL."""

    status_opcodes = (
        GenericOnOffOpcode.GENERIC_ONOFF_STATUS,
        LightLightnessOpcode.LIGHT_LIGHTNESS_STATUS,
        LightCTLOpcode.LIGHT_CTL_STATUS,
        LightCTLOpcode.LIGHT_CTL_TEMPERATURE_RANGE_STATUS,
    )

    model_id = BtMeshModelId.LightCTLServer

    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP}
    _attr_supported_features = LightEntityFeature.TRANSITION

    _attr_available = False
    _attr_min_color_temp_kelvin = DEFAULT_MIN_KELVIN
    _attr_max_color_temp_kelvin = DEFAULT_MAX_KELVIN

    _last_state: tuple[int, int] | None = None
    _flag_update_temperature_range = True

    def status_onoff_to_ctl(self, onoff_status: Container):
        """Convert GenericOnOff status to the LightCTL based on last state."""
        is_on = BtMeshLightEntity.extract_generic_onoff_status(onoff_status)
        if is_on is not None:
            if self._last_state is not None:
                present_ctl_lightness = self._last_state[0] if is_on else 0
                present_ctl_temperature = self._last_state[1]
            else:
                present_ctl_lightness = (
                    self.brightness_hass_to_btmesh(DEFAULT_LIGHT_BRIGHTNESS)
                    if is_on
                    else 0
                )
                present_ctl_temperature = DEFAULT_LIGHT_TEMPERATURE
            return Container(
                present_ctl_lightness=present_ctl_lightness,
                present_ctl_temperature=present_ctl_temperature,
            )
        else:
            return None

    def status_lightness_to_ctl(self, light_lightness_status: Container):
        """Convert LightLightnessf status to the LightCTL based on last state."""
        lightness = BtMeshLightEntity.extract_light_lightness_status(
            light_lightness_status
        )
        if lightness is not None:
            if self._last_state is not None:
                present_ctl_temperature = self._last_state[1]
            else:
                present_ctl_temperature = DEFAULT_LIGHT_TEMPERATURE
            return Container(
                present_ctl_lightness=lightness,
                present_ctl_temperature=present_ctl_temperature,
            )
        else:
            return None

    def update_entity_state(self, light_ctl_status: Container):
        """Extract light state from LightCTL model status."""
        state = BtMeshLightEntity.extract_light_ctl_status(
            light_ctl_status
        )
        if state is not None:
            lightness, temperature = state
            self._attr_brightness = BtMeshLightEntity.brightness_btmesh_to_hass(lightness)
            self._attr_color_temp_kelvin = temperature
            self._attr_is_on = self._attr_brightness > 0
            self._attr_available = True
            if lightness > 0:
                self._last_state = state
        else:
            self._attr_available = False

    def receive_message(
        self,
        source: int,
        app_index: int,
        destination: Union[int, UUID],
        message: ParsedMeshMessage
    ):
        """Receive status reports from LightCTL model."""
        opcode_name = BtMeshOpcode.get(message.opcode).name.lower()
        match message.opcode:
            case GenericOnOffOpcode.GENERIC_ONOFF_STATUS:
                model_state = self.status_onoff_to_ctl(
                    message.generic_onoff_status
                )
                self.update_model_state(model_state)
                self.update_entity_state(model_state)
                self.async_write_ha_state()
            case LightLightnessOpcode.LIGHT_LIGHTNESS_STATUS:
                model_state = self.status_lightness_to_ctl(
                    message.light_lightness_status
                )
                self.update_model_state(model_state)
                self.update_entity_state(model_state)
                self.async_write_ha_state()
            case LightCTLOpcode.LIGHT_CTL_STATUS:
                self.update_entity_state(message.light_ctl_status)
                self.async_write_ha_state()
                super().receive_message(source, app_index, destination, message)
            case LightCTLOpcode.LIGHT_CTL_TEMPERATURE_RANGE_STATUS:
                self._attr_min_color_temp_kelvin = message[opcode_name].range_min
                self._attr_max_color_temp_kelvin = message[opcode_name].range_max
            case _:
                pass

    async def query_model_state(self) -> any:
        """Get LightCTL state."""
        if self._flag_update_temperature_range:
            result = await self.app.light_ctl_temperature_range_get(
                destination=self.unicast_addr,
                app_index=self.app_key,
            )
            if result is not None:
                self._attr_min_color_temp_kelvin = result.range_min
                self._attr_max_color_temp_kelvin = result.range_max
                self._flag_update_temperature_range = False

        return await self.app.light_ctl_get(
            destination=self.unicast_addr,
            app_index=self.app_key,
        )

    async def async_update(self) -> None:
        """Update LightEntity state from latest LightCTL."""
        self.update_entity_state(self.model_state)

    async def light_ctl_set(
        self,
        lightness: int,
        temperature: int,
        transition_time: float = None
    ) -> None:
        """Set LightCTL state"""
        result = await self.app.light_ctl_set(
            destination=self.unicast_addr,
            app_index=self.app_key,
            ctl_lightness=lightness,
            ctl_temperature=temperature,
            transition_time=transition_time,
        )
        if result is not None:
            self.update_model_state(result)
        else:
            self.update_model_state(
                Container(
                    present_ctl_lightness=lightness,
                    present_ctl_temperature=temperature
                )
            )
        self.invalidate_device_state()

    async def async_turn_on(self, **kwargs):
        """Turn the specified light on."""

        transition_time = (
            int(kwargs[ATTR_TRANSITION])
            if ATTR_TRANSITION in kwargs
            else None
        )

        if ATTR_BRIGHTNESS in kwargs or ATTR_COLOR_TEMP_KELVIN in kwargs:
            arg_brightness = kwargs.get(ATTR_BRIGHTNESS, self._attr_brightness)
            arg_color_temp_kelvin = kwargs.get(
                ATTR_COLOR_TEMP_KELVIN,
                self._attr_color_temp_kelvin
            )

            if arg_brightness is not None and arg_color_temp_kelvin is not None:
                lightness = BtMeshLightEntity.brightness_hass_to_btmesh(arg_brightness)
                temperature = arg_color_temp_kelvin

                await self.light_ctl_set(
                    lightness=lightness,
                    temperature=temperature,
                    transition_time=transition_time
                )
        else:
            await self.app.generic_onoff_set(
                destination=self.unicast_addr,
                app_index=self.app_key,
                onoff=1,
                transition_time=transition_time)

            self.update_model_state(
                self.status_onoff_to_ctl(
                    Container(
                        present_onoff=1
                    )
                )
            )
            self.invalidate_device_state()
        self._flag_update_temperature_range = True

    async def async_turn_off(self, **kwargs):
        """Turn the specified light off."""

        transition_time = (
            int(kwargs[ATTR_TRANSITION])
            if ATTR_TRANSITION in kwargs
            else None
        )

        await self.app.generic_onoff_set(
            destination=self.unicast_addr,
            app_index=self.app_key,
            onoff=0,
            transition_time=transition_time
        )
        self.update_model_state(
            self.status_onoff_to_ctl(
                Container(
                    present_onoff=0
                )
            )
        )
        self.invalidate_device_state()
        self._flag_update_temperature_range = True


class BtMeshLight_LightHSL(BtMeshLightEntity):
    """Representation of a BT Mesh LightHSL."""

    status_opcodes = (
        GenericOnOffOpcode.GENERIC_ONOFF_STATUS,
        LightLightnessOpcode.LIGHT_LIGHTNESS_STATUS,
        LightHSLOpcode.LIGHT_HSL_STATUS,
        LightHSLOpcode.LIGHT_HSL_TARGET_STATUS,
    )

    model_id = BtMeshModelId.LightHSLServer

    _attr_color_mode = ColorMode.HS
    _attr_supported_color_modes = {ColorMode.HS}
    _attr_supported_features = LightEntityFeature.TRANSITION

    _attr_available = False

    _last_state: tuple[int, int, int] | None = None

    def status_onoff_to_hsl(self, onoff_status: Container):
        """Convert GenericOnOff status to the LightHSL based on last state."""
        is_on = BtMeshLightEntity.extract_generic_onoff_status(onoff_status)
        if is_on is not None:
            if self._last_state is not None:
                lightness = self._last_state[0] if is_on else 0
                hue = self._last_state[1]
                saturation = self._last_state[2]
            else:
                lightness = (
                    self.brightness_hass_to_btmesh(DEFAULT_LIGHT_BRIGHTNESS)
                    if is_on
                    else 0
                )
                hue = 0
                saturation = 0
            return Container(
                hsl_lightness=lightness,
                hsl_hue=hue,
                hsl_saturation=saturation
            )
        else:
            return None

    def status_lightness_to_hsl(self, light_lightness_status: Container):
        """Convert LightLightnessf status to the LightHSL based on last state."""
        lightness = BtMeshLightEntity.extract_light_lightness_status(
            light_lightness_status
        )
        if lightness is not None:
            if self._last_state is not None:
                hue = self._last_state[1]
                saturation = self._last_state[2]
            else:
                hue = 0
                saturation = 0
            return Container(
                hsl_lightness=lightness,
                hsl_hue=hue,
                hsl_saturation=saturation
            )
        else:
            return None

    def update_entity_state(self, light_hsl_status: Container):
        """Extract light state from LightHSL model status."""
        state = BtMeshLightEntity.extract_light_hsl_status(
            light_hsl_status
        )
        if state:
            self._attr_brightness = BtMeshLightEntity.brightness_btmesh_to_hass(
                state[0]
            )
            self._attr_hs_color = BtMeshLightEntity.color_btmesh_to_hass(
                state[1],
                state[2]
            )
            self._attr_is_on = self._attr_brightness > 0
            self._attr_available = True

            if self._last_state is None or self.model_state.hsl_lightness > 0:
                self._last_state = state
        else:
            self._attr_available = False

    def receive_message(
        self,
        source: int,
        app_index: int,
        destination: Union[int, UUID],
        message: ParsedMeshMessage
    ):
        """Receive status reports from LightCTL model."""
        match message.opcode:
            case GenericOnOffOpcode.GENERIC_ONOFF_STATUS:
                model_state = self.status_onoff_to_hsl(
                    message.generic_onoff_status
                )
                self.update_model_state(model_state)
                self.update_entity_state(model_state)
                self.async_write_ha_state()
            case LightLightnessOpcode.LIGHT_LIGHTNESS_STATUS:
                model_state = self.status_lightness_to_hsl(
                    message.light_lightness_status
                )
                self.update_model_state(model_state)
                self.update_entity_state(model_state)
                self.async_write_ha_state()
            case LightHSLOpcode.LIGHT_HSL_STATUS:
                self.update_entity_state(message.light_hsl_status)
                self.async_write_ha_state()
                super().receive_message(source, app_index, destination, message)
            case LightHSLOpcode.LIGHT_HSL_TARGET_STATUS:
                self.update_entity_state(message.light_hsl_target_status)
                self.async_write_ha_state()
                super().receive_message(source, app_index, destination, message)
            case _:
                pass

    async def async_update(self) -> None:
        """Update LightEntity state from latest LightHSL."""
        self.update_entity_state(self.model_state)

    async def query_model_state(self) -> any:
        """Get LightHSL state."""
        return await self.app.light_hsl_get_target(
            destination=self.unicast_addr,
            app_index=self.app_key,
        )

    async def light_hsl_set(
        self,
        lightness: int,
        hue: int,
        saturation: int,
        transition_time: float = None
    ) -> None:
        """Set LightHSL lightness, hue and saturation"""
        result = await self.app.light_hsl_set(
            destination=self.unicast_addr,
            app_index=self.app_key,
            hsl_lightness=lightness,
            hsl_hue=hue,
            hsl_saturation=saturation,
            transition_time=transition_time,
        )
        if result is not None:
            self.update_model_state(result)
        else:
            self.update_model_state(
                Container(
                    hsl_lightness=lightness,
                    hsl_hue=hue,
                    hsl_saturation=saturation
                )
            )
        self.invalidate_device_state()

    async def async_turn_on(self, **kwargs):
        """Turn the specified light on."""

        transition_time = (
            int(kwargs[ATTR_TRANSITION])
            if ATTR_TRANSITION in kwargs
            else None
        )

        if ATTR_BRIGHTNESS in kwargs or ATTR_HS_COLOR in kwargs:
            arg_brightness = kwargs.get(ATTR_BRIGHTNESS, self._attr_brightness)
            arg_color = kwargs.get(ATTR_HS_COLOR, self._attr_hs_color)

            if arg_brightness is not None and arg_color is not None:
                lightness = BtMeshLightEntity.brightness_hass_to_btmesh(arg_brightness)
                (hue, saturation) = BtMeshLightEntity.color_hass_to_btmesh(arg_color)

                await self.light_hsl_set(
                    lightness=lightness,
                    hue=hue,
                    saturation=saturation,
                    transition_time=transition_time
                )
        else:
            await self.app.generic_onoff_set(
                destination=self.unicast_addr,
                app_index=self.app_key,
                onoff=1,
                transition_time=transition_time
            )

            self.update_model_state(
                self.status_onoff_to_hsl(
                    Container(
                        present_onoff=1
                    )
                )
            )
            self.invalidate_device_state()

    async def async_turn_off(self, **kwargs):
        """Turn the specified light off."""

        transition_time = (
            int(kwargs[ATTR_TRANSITION])
            if ATTR_TRANSITION in kwargs
            else None
        )

        await self.app.generic_onoff_set(
            destination=self.unicast_addr,
            app_index=self.app_key,
            onoff=0,
            transition_time=transition_time
        )

        self.update_model_state(
            self.status_onoff_to_hsl(
                Container(
                    present_onoff=1
                )
            )
        )
        self.invalidate_device_state()


class BtMeshLightEntityFactory(object):
    @staticmethod
    def get(model_id: int) -> object:
        if type(model_id) is not BtMeshModelId:
            raise ValueError("model_id must be int")

        raw_subclasses_ = BtMeshLightEntity.__subclasses__()
        classes: dict[int, Callable[..., object]] = {
            c.model_id: c for c in raw_subclasses_
        }
        class_ = classes.get(model_id, None)
        if class_ is not None:
            return class_

        raise ClassNotFoundError
