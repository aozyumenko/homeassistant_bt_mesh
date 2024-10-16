"""Config flow for BT Mesh."""

import asyncio
import async_timeout

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
import voluptuous as vol
from .const import (
    DOMAIN,
    BT_MESH_CONFIG,
    CONF_DBUS_APP_PATH,
    CONF_DBUS_APP_TOKEN,
    CONF_MESH_CFGCLIENT_CONFIG_PATH,
    DEFAULT_MESH_JOIN_TIMEOUT
)
from .bt_mesh import BtMeshApplication

import logging
_LOGGER = logging.getLogger(__name__)



class BtMeshConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Bluetooth Mesh config flow."""


    def __init__(self):
        _LOGGER.debug("BtMeshConfigFlow::init()")
        self.pin = None
        self.config = None
        self.bt_mesh = None
        self.join_task = None
        self.pin = None
        self.token = None


    async def async_step_user(self, user_input=None) -> FlowResult:
        _LOGGER.debug("async_step_user: cur_step=%s, user_input=%s" % (self.cur_step, user_input))

        # export domain config
        if self.config is None:
            entry_data = self.hass.data[DOMAIN]
            self.config = entry_data[BT_MESH_CONFIG]

        # create BT Mesh application
        _LOGGER.debug("async_step_user: bt_mesh=%s" % (self.bt_mesh))
        if self.bt_mesh is None:
            self.bt_mesh = BtMeshApplication(
                path=self.config[CONF_DBUS_APP_PATH]
            )

        if self.join_task is None:
            # start join and provision task
            self.join_task = self.hass.async_create_task(
                self._task_join_routine(user_input)
            )

        return self.async_show_progress(
            step_id="join_start",
            progress_action="join_start",
        )


    async def async_step_join_start(self, user_input):
        _LOGGER.error("join_start(): user_input=%s" % (user_input))

        try:
            self.pin = user_input["pin"]
            return self.async_show_progress_done(next_step_id="join_pin_show")
        except Exception as err:
            return self.async_show_progress_done(next_step_id="join_failed")


    async def async_step_join_failed(self, user_input):
        _LOGGER.error("join_failed(): user_input=%s" % (user_input))
        return self.async_abort(reason="join_failed")


    async def async_step_join_pin_show(self, user_input):
        _LOGGER.error("join_pin_show(): user_input=%s" % (user_input))
        schema = vol.Schema({vol.Required("pin", default=self.pin): str})
        return self.async_show_form(
            step_id="join_finish", data_schema=schema
        )


    async def async_step_join_finish(self, user_input):
        if self.token is not None:
            _LOGGER.info("Join finished, token %x" % (self.token))
            return self.async_create_entry(
                title = "Bluetooth Mesh Integration",
                data = {
                    CONF_DBUS_APP_PATH: self.config[CONF_DBUS_APP_PATH],
                    CONF_DBUS_APP_TOKEN: self.token,
                    CONF_MESH_CFGCLIENT_CONFIG_PATH: self.config[ CONF_MESH_CFGCLIENT_CONFIG_PATH]
                }
            )
        else:
            _LOGGER.info("Join failed: invalid token")
            return self.async_abort(reason="join_token_invalid")


    # async join tasks
    async def _task_join_routine(self, user_input: dict):
        _LOGGER.debug("_task_join(): start")

        try:
            async with async_timeout.timeout(DEFAULT_MESH_JOIN_TIMEOUT):
                try:
                    self.token = await self.bt_mesh.mesh_join(self)
                except Exception as err:
                    _LOGGER.error("Join failed: %s::%s", err, err.__class__.__name__)
        except:
            _LOGGER.info("Join timeout expired")
            pass
        finally:
            if self.cur_step['step_id'] == "join_start":
                self.hass.async_create_task(
                    self.hass.config_entries.flow.async_configure(
                        flow_id=self.flow_id, user_input=user_input
                    )
                )


    def _cb_display_numeric(self, type: str, number: int):
        _LOGGER.debug("Display numeric, type: %s, number: %d" % (type, number))

        user_input = {}

        if type == "out-numeric":
            user_input["pin"] = str(number)

        self.hass.async_create_task(
            self.hass.config_entries.flow.async_configure(
                flow_id=self.flow_id, user_input=user_input
            )
        )
