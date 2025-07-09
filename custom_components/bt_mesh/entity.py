from bluetooth_numbers import company
from .product import product

from homeassistant.helpers.entity import Entity, DeviceInfo

from . import BtMeshModelId
from .application import BtMeshApplication
from .mesh_cfgclient_conf import MeshCfgModel

from ..const import DOMAIN


#import logging
#_LOGGER = logging.getLogger(__name__)


class ClassNotFoundError(Exception):
    """Factory could not find the class."""


class BtMeshEntity(Entity):
    """Basic representation of a BT Mesh service."""
    app: BtMeshApplication
    cfg_model: MeshCfgModel
    passive: bool

    def __init__(
        self,
        app: BtMeshApplication,
        cfg_model: MeshCfgModel,
        passive: bool
    ) -> None:
        """Initialize the device."""
        self.app = app
        self.cfg_model = cfg_model
        self.passive = passive

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(self.cfg_model.device.unique_id))},
            #name=str(self.cfg_model.device.unique_id),
            name=f"{DOMAIN}_{self.cfg_model.device.unicast_addr:04x}",
            manufacturer=company[self.cfg_model.device.cid] \
                if self.cfg_model.device.cid in company \
                    else f"{self.cfg_model.device.cid:04x}",
            model=product[self.cfg_model.device.pid] \
                if self.cfg_model.device.pid in product \
                    else f"{self.cfg_model.device.pid:04x}",
            model_id=f"{self.cfg_model.device.pid:04x}",
            sw_version=f"{self.cfg_model.device.vid:04x}",
        )
        self._attr_unique_id = self.cfg_model.unique_id
        self._attr_name = self.cfg_model.name
