"""..."""
import logging

import asyncio

from homeassistant import config_entries
import voluptuous as vol
from .const import DOMAIN
from .bt_mesh import BtMeshApplication



_LOGGER = logging.getLogger(__name__)



class BtMeshConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Bluetooth Mesh config flow."""

    join_task = None

    def __init__(self):
        self.token = None
        self.pin = None
        self._bt_mesh = None
        _LOGGER.error("BtMeshConfigFlow: new class")

    async def async_step_user(self, user_input):
        _LOGGER.error("async_step_user: cur_step=%s, %s" % (self.cur_step, user_input))

        if user_input is not None:
            pass  # TODO: process info

        if user_input is None:
            return self._join_start(user_input)

#        if self.token is None:
#            return await self.async_step_join_start()

        my_list = ["one", "two", "three"]
        #schema = vol.Schema({vol.Required("password"): str})
        schema = vol.Schema({vol.Required("path"): vol.In(my_list)})
        return self.async_show_form(
            step_id="user", data_schema=schema
        )




    #######################################

    def _join_start(self, user_input):
        if self._bt_mesh is None:
            self._bt_mesh = BtMeshApplication()

        _LOGGER.error("_join_start() test, self.join_task=%s" % (self.join_task.__class__.__name__))
        if not self.join_task:
            self.join_task = self.hass.async_create_task(
                self._task_join()
            )

            _LOGGER.error("async_step_join_start(), self.join_task=%s" % (self.join_task.__class__.__name__))
            return self.async_show_progress(
                step_id="join_pin_wait", progress_action="join_start"
            )

        #?????
        #try:
        #    await self.join_task
        #except Exception as err:  # pylint: disable=broad-except
        #    _LOGGER.exception("... : %s", err)
        #    return self.async_show_progress_done(next_step_id="join_failed")
        return self.async_abort(reason="join_failed2")




    async def async_step_join_pin_wait(self, user_input):
        _LOGGER.error("join_pin_wait(): user_input=%s" % (user_input))
        self.pin = user_input["pin"]
        return self.async_show_progress_done(next_step_id="join_pin_show")


    async def async_step_join_pin_show(self, user_input):
        _LOGGER.error("join_pin_show(): user_input=%s" % (user_input))
        schema = vol.Schema({vol.Required("pin", default=self.pin): str})
        return self.async_show_form(
            step_id="join_finish", data_schema=schema
        )


    async def async_step_join_finish(self, user_input):
        if self.token is not None:
            return self.async_create_entry(
                title = "",
                data = {
                    # TODO: add UUID
                    "token": self.token
                }
            )
        else:
            _LOGGER.error("join_finish(): invalid token")
            return self.async_abort(reason="join_token_invalid")



   ##################################
   # async join tasks

    def _cb_display_numeric(self, type: str, number: int):
        _LOGGER.error("display_numeric: type=%s, number=%d" % (type, number))
        if type == "out-numeric":
            self.hass.async_create_task(
                self.hass.config_entries.flow.async_configure(
                    flow_id=self.flow_id, user_input={ "pin": str(number)}
                )
            )
        else:
            self.hass.async_create_task(
                self.hass.config_entries.flow.async_abort(
                    flow_id=self.flow_id
                )
            )


    # FIxMe: _task_join_routine
    async def _task_join(self):
        _LOGGER.error("_task_join(): start")
        try:
            token = await self._bt_mesh.mesh_join(self)
            _LOGGER.error("_task_join(): token=%s", token)
        except Exception as err:
            _LOGGER.error("_task_join() error: %s::%s", err, err.__class__.__name__)
            # does not work
            return self.async_abort(reason="join_failed")
        finally:
            _LOGGER.error("_task_join(): finally, token=%s", token)
            self.token = token

    ####################################################################
