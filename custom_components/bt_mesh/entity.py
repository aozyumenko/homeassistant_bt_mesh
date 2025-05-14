from homeassistant.helpers.entity import Entity, DeviceInfo

from . import BtMeshModelId
from .application import BtMeshApplication

from ..const import (
    DOMAIN,     # TODO: change const to init argument
)


class BtMeshEntity(Entity):
    """Basic representation of a BT Mesh service."""

    _application: BtMeshApplication
    _state_cache: dict or None

    def __init__(self, application, uuid, cid, pid, vid, addr, model_id, app_index):
        """Initialize the device."""
        self._application = application
        self._unicast_addr = addr
        self._model_id = model_id
        self._app_index = app_index

        self.uuid: str = uuid
        self.cid: int = cid
        self.pid: int = pid
        self.vid: int = vid
        self.product: str = "0x%04x" % (self.pid)
        self.company: str = "0x%04x" % (self.cid)

        self._attr_name = "%04x-%s" % (self._unicast_addr, BtMeshModelId.get_name(model_id))
        self._attr_unique_id = "%04x-%04x-%s" % (self._unicast_addr, self._model_id, uuid)

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.uuid)},
            name=self.uuid,
            model=self.product,
            manufacturer=self.company,
            sw_version=("0x%04x") % self.vid,
        )

        self._state_cache = None;


    @property
    def unicast_addr(self):
        """Return the unicast address of the node."""
        return self._unicast_addr

    @property
    def model_id(self):
        """Return the Model Id."""
        return self._model_id

    @property
    def app_index(self):
        """Return the application key index of the model."""
        return self._app_index

    @property
    def application(self):
        """Return the BT Mesh Client application."""
        return self._application


    # state cache
    def cache_update(self, state: dict):
        self._state_cache = { 'last_update': time.time(), 'state': state }

    def cache_get(self) -> dict or None:
        if self._state_cache is None:
            return None
        elif (self._state_cache['last_update'] + G_MESH_CACHE_INVALIDATE_TIMEOUT) < time.time():
            self._state_cache = None
            return None
        else:
            return self._state_cache['state']

    # BT Mesh Application interface
