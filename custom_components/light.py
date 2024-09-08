"""BT MESH light"""
from __future__ import annotations

import math
import asyncio

from homeassistant.components import light
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_EFFECT,
    ATTR_HS_COLOR,
    ATTR_TRANSITION,
    ATTR_WHITE,
    ColorMode,
    LightEntity,
    LightEntityFeature,
    brightness_supported,
)
#from homeassistant.config_entries import ConfigEntry
#from homeassistant.core import HomeAssistant, callback
#from homeassistant.helpers.dispatcher import async_dispatcher_connect
#from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BtMeshEntity
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
    """Set up BT Mesh light entry."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    application = entry_data[BT_MESH_APPLICATION]
    mesh_cfgclient_conf = entry_data[BT_MESH_CFGCLIENT_CONF]

    entities = []
    devices = mesh_cfgclient_conf.devices
#    _LOGGER.debug("devices=%s" % (devices))
    for device in devices:
        try:
            device_unicat_addr = device['unicastAddress']

            # set BT Mesh Light servers priority
            light_model_id_list = (
                BtMeshModelId.LightHSLSetupServer,
                BtMeshModelId.LightCTLSetupServer,
                BtMeshModelId.LightLightnessSetupServer
            )

            element_id_in_use = []
            for light_model_id in light_model_id_list:
                for light in device['models'][light_model_id]:
                    if light[ELEMENT_MAIN] in element_id_in_use:
                        continue
                    element_id_in_use.append(light[ELEMENT_MAIN])

                    element_idx = light[ELEMENT_MAIN]
                    element_unicast_addr = device_unicat_addr + element_idx
                    app_key = device['app_keys'][element_idx][BtMeshModelId.GenericOnOffServer]
#                    _LOGGER.debug("model_id=%s, uuid=%s, %d, addr=0x%04x, app_key=%d" % (light_model_id, device['UUID'], element_idx, element_unicast_addr, app_key))

                    if light_model_id == BtMeshModelId.LightCTLSetupServer:
                        entities.append(
                            BtMeshLight_LightCTL(
                                application=application,
                                uuid=device['UUID'],
                                cid=device['cid'],
                                pid=device['pid'],
                                vid=device['vid'],
                                addr=element_unicast_addr,
                                model_id=light_model_id,
                                app_index=app_key
                            )
                        )
                    elif light_model_id == BtMeshModelId.LightHSLSetupServer:
                        entities.append(
                            BtMeshLight_LightHSL(
                                application=application,
                                uuid=device['UUID'],
                                cid=device['cid'],
                                pid=device['pid'],
                                vid=device['vid'],
                                addr=element_unicast_addr,
                                model_id=light_model_id,
                                app_index=app_key
                            )
                        )
        except KeyError:
            continue

    add_entities(entities)

    #application.onoff_init_receive_status()

    return True




#class BtMeshLight_LightLightness(BtMeshEntity, SwitchEntity):


class BtMeshLight_LightCTL(BtMeshEntity, LightEntity):
    """Representation of a BT Mesh LightCTL."""

    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP}
    _attr_supported_features = LightEntityFeature.TRANSITION

    _req_lock = asyncio.Lock()

    def __init__(self, **kwds: Any) -> None:
        """Initialize BT Mesh LightCTL."""

        super().__init__(
            **kwds,
        )

    async def async_update(self) -> None:
        try:
            async with self._req_lock:
                result = await self.application.mesh_light_ctl_get(self.unicast_addr, self.app_index)
                self._attr_is_on = result['present_ctl_lightness'] > 0
                self._attr_brightness = int(result['present_ctl_lightness'] / 256)
                self._attr_color_temp = math.ceil(1000000 / result['present_ctl_temperature'])
        except Exception:
#            _LOGGER.debug("failed to get LightCTL status: addr %04x, app_index %d" %
#                          (self.unicast_addr, self.app_index))
            self._attr_is_on = None
            self._attr_brightness = None
            self._attr_color_temp = None

        try:
            async with self._req_lock:
                result = await self.application.mesh_light_ctl_temperature_range_get(self.unicast_addr, self.app_index)
            if not result is None:
                self._attr_max_mireds = math.ceil(1000000 / result['range_min'])
                self._attr_min_mireds = math.ceil(1000000 / result['range_max'])
        except Exception:
#            _LOGGER.debug("failed to get LightCTL Temperature Range status: addr %04x, app_index %d" %
#                          (self.unicast_addr, self.app_index))
            pass

    async def async_turn_on(self, **kwargs):
        """Turn the specified light on."""

        self._attr_is_on = True
        if len(kwargs) == 0:
            try:
                async with self._req_lock:
                    await self.application.mesh_generic_onoff_set(self.unicast_addr, self.app_index, 1)
            except Exception:
                self._attr_is_on = True
            else:
                self._attr_is_on = None
        else:
            if ATTR_BRIGHTNESS in kwargs:
                self._attr_brightness = kwargs[ATTR_BRIGHTNESS]

            if ATTR_COLOR_TEMP in kwargs:
                self._attr_color_temp = kwargs[ATTR_COLOR_TEMP]

            if self._attr_brightness and self._attr_color_temp:
                ligthness = self._attr_brightness * 256
                temperature = math.ceil(1000000 / self._attr_color_temp)

                async with self._req_lock:
                    await self.application.mesh_light_ctl_set(self.unicast_addr, self.app_index, ligthness, temperature)


    async def async_turn_off(self, **kwargs):
        """Turn the specified light off."""
        self._attr_is_on = False

        async with self._req_lock:
            await self.application.mesh_generic_onoff_set(self.unicast_addr, self.app_index, 0)


class BtMeshLight_LightHSL(BtMeshEntity, LightEntity):
    """Representation of a BT Mesh LightHSL."""

    _attr_color_mode = ColorMode.HS
    _attr_supported_color_modes = {ColorMode.HS}
    _attr_supported_features = LightEntityFeature.TRANSITION

    _req_lock = asyncio.Lock()


    def __init__(self, **kwds: Any) -> None:
        """Initialize BT Mesh LightCTL."""

        self._attr_is_on = None

        super().__init__(
            **kwds,
        )

    async def async_update(self) -> None:
        try:
            async with self._req_lock:
                result = await self.application.mesh_light_hsl_get(self.unicast_addr, self.app_index)
            self._attr_is_on = result['hsl_lightness'] > 0
            self._attr_brightness = math.ceil(result['hsl_lightness'] / 256.0)
            self._attr_hs_color = [
                math.ceil(result['hsl_hue'] * 360. / 65535.0),
                math.ceil(result['hsl_saturation'] * 100.0 / 65535.0)
            ]
#            _LOGGER.debug("result=%s" % (result))
        except Exception as err:
#            _LOGGER.debug("failed to get LightHSL status: addr %04x, app_index %d (%s)" %
#                          (self.unicast_addr, self.app_index, err))
            self._attr_hs_color = None
            self._attr_brightness = None
            self._attr_is_on = None


    async def async_turn_on(self, **kwargs):
        """Turn the specified light on."""

#        _LOGGER.debug("_attr_is_on=%s" % (self._attr_is_on))
        if self._attr_is_on is None:
            return

        if len(kwargs) == 0:
            self._attr_is_on = True
            async with self._req_lock:
                await self.application.mesh_generic_onoff_set(self.unicast_addr, self.app_index, 1)
        else:
            if ATTR_BRIGHTNESS in kwargs:
                self._attr_brightness = kwargs[ATTR_BRIGHTNESS]

            if ATTR_HS_COLOR in kwargs:
                self._attr_hs_color = kwargs[ATTR_HS_COLOR]

            if self._attr_brightness and self._attr_hs_color:
                ligthness = self._attr_brightness * 256
                hue = math.ceil(self._attr_hs_color[0] * 65535.0 / 360.0)
                saturation = math.ceil(self._attr_hs_color[1] * 65535.0 / 100.0)

                async with self._req_lock:
                    await self.application.mesh_light_hsl_set(
                        self.unicast_addr,
                        self.app_index,
                        ligthness,
                        hue,
                        saturation
                    )

    async def async_turn_off(self, **kwargs):
        """Turn the specified light off."""
        self._attr_is_on = False

        async with self._req_lock:
            await self.application.mesh_generic_onoff_set(self.unicast_addr, self.app_index, 0)
