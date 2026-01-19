"""BT MESH light"""
from __future__ import annotations

import math
import asyncio
from construct import Container

from bluetooth_mesh.models.generic.onoff import GenericOnOffClient
from bluetooth_mesh.models.light.lightness import LightLightnessClient
from bluetooth_mesh.models.light.ctl import LightCTLClient
from bluetooth_mesh.models.light.hsl import LightHSLClient
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

from bt_mesh_ctrl import BtMeshModelId, BtMeshOpcode
#from bt_mesh_ctrl import BtMeshModelId, BtSensorAttrPropertyId
from bt_mesh_ctrl.mesh_cfgclient_conf import MeshCfgModel

from .entity import BtMeshEntity, ClassNotFoundError
from .const import (
    BT_MESH_DISCOVERY_ENTITY_NEW,
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
    """Set up BT Mesh light entry."""

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

    async def generic_onoff_set(self, state:int, transition_time:float=None) -> None:
        """Set GenericOnOff state"""
        try:
            client = self.app.elements[0][GenericOnOffClient]
            await client.set(
                destination=self.unicast_addr,
                app_index=self.app_key,
                onoff=state,
                delay=None if transition_time is None else 0,
                transition_time=transition_time,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT,
            )
        except asyncio.TimeoutError:
            pass

class BtMeshLight_LightLightness(BtMeshLightEntity):
    """Representation of a BT Mesh LightLightness."""

    status_opcodes = (
        LightLightnessOpcode.LIGHT_LIGHTNESS_STATUS,
    )

    model_id = BtMeshModelId.LightLightnessServer

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_supported_features = LightEntityFeature.TRANSITION

    _attr_available = False
    _last_state: int | None = None

    async def query_model_state(self) -> any:
        """Get LightLightness state"""
        client = self.app.elements[0][LightLightnessClient]
        try:
            return await client.get(
                destination=self.unicast_addr,
                app_index=self.app_key,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT,
            )
        except asyncio.TimeoutError:
            pass
        return None

    async def async_update(self) -> None:
        if self.model_state is not None:
            if "remaining_time" in self.model_state and self.model_state.remaining_time > 0:
                lightness = self.model_state.target_lightness
            else:
                lightness = self.model_state.present_lightness
            self._attr_brightness = BtMeshLightEntity.brightness_btmesh_to_hass(lightness)
            self._attr_is_on = self._attr_brightness > 0
            self._attr_available = True

            if lightness > 0:
                self._last_state = lightness
        else:
            self._attr_available = False

    async def light_lightness_set(self, lightness:int, transition_time:float=None) -> None:
        """Set LightLightness lightness"""
        try:
            client = self.app.elements[0][LightLightnessClient]
            result = await client.set(
                destination=self.unicast_addr,
                app_index=self.app_key,
                lightness=lightness,
                delay=None if transition_time is None else 0,
                transition_time=transition_time,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT,
            )
            self.update_model_state(result)
        except asyncio.TimeoutError:
            self.update_model_state(Container(present_lightness=lightness))
        self.invalidate_device_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        transition_time = int(kwargs[ATTR_TRANSITION]) if ATTR_TRANSITION in kwargs else None
#        _LOGGER.debug(f"async_turn_on(): transition_time = {transition_time}")

        if ATTR_BRIGHTNESS in kwargs:
            await self.light_lightness_set(
                BtMeshLightEntity.brightness_hass_to_btmesh(kwargs[ATTR_BRIGHTNESS]),
                transition_time=transition_time
            )
        else:
            await self.generic_onoff_set(1, transition_time=transition_time)

            # hack that allows us to use GenericOnOff instead of
            # LightLighting to turn on the light
            if self._last_state:
                self.update_model_state(Container(present_lightness=self._last_state))
            self.invalidate_device_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        transition_time = int(kwargs[ATTR_TRANSITION]) if ATTR_TRANSITION in kwargs else None
#        _LOGGER.debug(f"async_turn_off(): transition_time = {transition_time}")
        await self.light_lightness_set(0, transition_time=transition_time)


class BtMeshLight_LightCTL(BtMeshLightEntity):
    """Representation of a BT Mesh LightCTL."""

    status_opcodes = (
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


    def receive_message(
        self,
        source: int,
        app_index: int,
        destination: Union[int, UUID],
        message: ParsedMeshMessage
    ):
        """..."""
        opcode_name = BtMeshOpcode.get(message.opcode).name.lower()
        match message.opcode:
            case LightCTLOpcode.LIGHT_CTL_STATUS:
                super().receive_message(source, app_index, destination, message)
            case LightCTLOpcode.LIGHT_CTL_TEMPERATURE_RANGE_STATUS:
                self._attr_min_color_temp_kelvin = message[opcode].range_min
                self._attr_max_color_temp_kelvin = message[opcode].range_max
            case _:
                pass

    async def async_update(self) -> None:
        if self.model_state is not None:
            if "remaining_time" in state and self.model_state.remaining_time > 0:
                lightness = self.model_state.target_ctl_lightness
                temperature = self.model_state.target_ctl_temperature
            else:
                lightness = self.model_state.present_ctl_lightness
                temperature = self.model_state.present_ctl_temperature
            self._attr_brightness = BtMeshLightEntity.brightness_btmesh_to_hass(lightness)
            self._attr_color_temp_kelvin = temperature
            self._attr_is_on = self._attr_brightness > 0
            self._attr_available = True

            if lightness > 0:
                self._last_state = [lightness, temperature]
        else:
            self._attr_available = False

        if self._flag_update_temperature_range:
            result = await self.light_ctl_temperature_range_get()
            if result is not None:
                self._attr_min_color_temp_kelvin = result.range_min
                self._attr_max_color_temp_kelvin = result.range_max
                self._flag_update_temperature_range = False

    async def query_model_state(self) -> any:
        """Get LightCTL state"""
        client = self.app.elements[0][LightCTLClient]
        try:
            return await client.get(
                destination=self.unicast_addr,
                app_index=self.app_key,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT,
            )
        except asyncio.TimeoutError:
            pass
        return None

    async def light_ctl_temperature_range_get(self) -> any:
        """Get LightCTL temperature range"""
        try:
            client = self.app.elements[0][LightCTLClient]
            return await client.temperature_range_get(
                destination=self.unicast_addr,
                app_index=self.app_key,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT,
            )
        except asyncio.TimeoutError:
            pass
        return None

    async def light_ctl_set(self, lightness, temperature, transition_time=None) -> None:
        """Set LightCTL state"""
        try:
            client = self.app.elements[0][LightCTLClient]
            result = await client.set(
                destination=self.unicast_addr,
                app_index=self.app_key,
                ctl_lightness=lightness,
                ctl_temperature=temperature,
                ctl_delta_uv=0,
                delay=None if transition_time is None else 0,
                transition_time=transition_time,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT
            )
            self.update_model_state(result)
        except asyncio.TimeoutError:
            self.update_model_state(
                Container(
                    present_ctl_lightness=lightness,
                    present_ctl_temperature=temperature
                )
            )
        self.invalidate_device_state()

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

                await self.light_ctl_set(
                    lightness,
                    temperature,
                    transition_time=transition_time
                )
        else:
            await self.generic_onoff_set(1,transition_time=transition_time)

            # hack that allows you to use GenericOnOff instead of
            # LightCTL to turn on the light
            if self._last_state:
                self.update_model_state(
                    Container(
                        present_ctl_lightness=self._last_state[0],
                        present_ctl_temperature=self._last_state[1],
                    )
                )
            self.invalidate_device_state()
        self._flag_update_temperature_range = True

    async def async_turn_off(self, **kwargs):
        """Turn the specified light off."""

        transition_time = int(kwargs[ATTR_TRANSITION]) if ATTR_TRANSITION in kwargs else None
#        _LOGGER.debug(f"async_turn_on(): transition_time = {transition_time}")

        await self.generic_onoff_set(0, transition_time=transition_time)

        # hack that allows you to use GenericOnOff instead of
        # LightCTL to turn on the light
        if self._last_state:
            self.update_model_state(
                Container(
                    present_ctl_lightness=0,
                    present_ctl_temperature=self._last_state[1],
                )
            )
        self.invalidate_device_state()
        self._flag_update_temperature_range = True


class BtMeshLight_LightHSL(BtMeshLightEntity):
    """Representation of a BT Mesh LightHSL."""

    status_opcodes = (
        LightHSLOpcode.LIGHT_HSL_STATUS,
        LightHSLOpcode.LIGHT_HSL_TARGET_STATUS,
    )

    model_id = BtMeshModelId.LightHSLServer

    _attr_color_mode = ColorMode.HS
    _attr_supported_color_modes = {ColorMode.HS}
    _attr_supported_features = LightEntityFeature.TRANSITION

    _attr_available = False

    _last_state: tuple[int, int, int] | None = None

    async def query_model_state(self) -> any:
        """Get LightHSL state"""
        client = self.app.elements[0][LightHSLClient]
        try:
            return await client.target_get(
                destination=self.unicast_addr,
                app_index=self.app_key,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT,
            )
        except asyncio.TimeoutError:
            pass
        return None

    async def async_update(self) -> None:
        if self.model_state is not None:
            self._attr_brightness = BtMeshLightEntity.brightness_btmesh_to_hass(self.model_state.hsl_lightness)
            self._attr_hs_color = BtMeshLightEntity.color_btmesh_to_hass(
                self.model_state.hsl_hue, self.model_state.hsl_saturation
            )
            self._attr_is_on = self._attr_brightness > 0
            self._attr_available = True

            if self.model_state.hsl_lightness > 0:
                self._last_state = (
                    self.model_state.hsl_lightness,
                    self.model_state.hsl_hue,
                    self.model_state.hsl_saturation
                )
        else:
            self._attr_available = False

    async def light_hsl_set(self, lightness, hue, saturation, transition_time=None) -> None:
        """Set LightHSL lightness, hue and saturation"""
        try:
            client = self.app.elements[0][LightHSLClient]
            result = await client.set(
                destination=self.unicast_addr,
                app_index=self.app_key,
                hsl_lightness=lightness,
                hsl_hue=hue,
                hsl_saturation=saturation,
                delay=None if transition_time is None else 0,
                transition_time=transition_time,
                send_interval=G_SEND_INTERVAL,
                timeout=G_TIMEOUT
            )
            self.update_model_state(result)
        except asyncio.TimeoutError:
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

        transition_time = int(kwargs[ATTR_TRANSITION]) if ATTR_TRANSITION in kwargs else None
#        _LOGGER.debug(f"async_turn_on(): transition_time = {transition_time}")

        if ATTR_BRIGHTNESS in kwargs or ATTR_HS_COLOR in kwargs:
            arg_brightness = kwargs.get(ATTR_BRIGHTNESS, self._attr_brightness)
            arg_color = kwargs.get(ATTR_HS_COLOR, self._attr_hs_color)

            if arg_brightness is not None and arg_color is not None:
                lightness = BtMeshLightEntity.brightness_hass_to_btmesh(arg_brightness)
                (hue, saturation) = BtMeshLightEntity.color_hass_to_btmesh(arg_color)

                await self.light_hsl_set(
                    lightness,
                    hue,
                    saturation,
                    transition_time=transition_time
                )
        else:
            await self.generic_onoff_set(1, transition_time=transition_time)

            # hack that allows you to use GenericOnOff instead of
            # LightHSL to turn off the light
            if self._last_state:
                self.update_model_state(
                    Container(
                        hsl_lightness=self._last_state[0],
                        hsl_hue=self._last_state[1],
                        hsl_saturation=self._last_state[2],
                    )
                )
            self.invalidate_device_state()

    async def async_turn_off(self, **kwargs):
        """Turn the specified light off."""

        transition_time = int(kwargs[ATTR_TRANSITION]) if ATTR_TRANSITION in kwargs else None
#        _LOGGER.debug(f"async_turn_on(): transition_time = {transition_time}")

        await self.generic_onoff_set(0, transition_time=transition_time)

        # hack that allows you to use GenericOnOff instead of
        # LightHSL to turn off the light
        if self._last_state:
            self.update_model_state(
                Container(
                    hsl_lightness=0,
                    hsl_hue=self._last_state[1],
                    hsl_saturation=self._last_state[2],
                )
            )
        self.invalidate_device_state()


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
