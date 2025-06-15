from bluetooth_numbers import company
from .product import product

from homeassistant.helpers.entity import Entity, DeviceInfo

from . import BtMeshModelId
from .application import BtMeshApplication
from .mesh_cfgclient_conf import MeshCfgModel

from ..const import DOMAIN


#import logging
#_LOGGER = logging.getLogger(__name__)



class BtMeshEntity(Entity):
    """Basic representation of a BT Mesh service."""
    app: BtMeshApplication
    cfg_model: MeshCfgModel

    def __init__(self, app: BtMeshApplication, cfg_model: MeshCfgModel) -> None:
        """Initialize the device."""
        self.app = app
        self.cfg_model = cfg_model

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(self.cfg_model.device.uuid))},
            manufacturer=company[self.cfg_model.device.cid] \
                if self.cfg_model.device.cid in company \
                    else f"{self.cfg_model.device.cid:04x}",
            model=product[self.cfg_model.device.pid] \
                if self.cfg_model.device.pid in product \
                    else f"{self.cfg_model.device.pid:04x}",
            model_id=f"{self.cfg_model.device.pid:04x}",
            sw_version=f"{self.cfg_model.device.vid:04x}",
        )
        self._attr_unique_id = f"{self.cfg_model.unicast_addr:04x}-{self.cfg_model.model_id:04x}-{str(self.cfg_model.device.uuid)}"
        self._attr_name = f"{self.cfg_model.unicast_addr:04x}-{BtMeshModelId.get_name(self.cfg_model.model_id)}"

#        _LOGGER.debug(self._attr_device_info)
#        _LOGGER.debug(self._attr_unique_id)
#        _LOGGER.debug(self._attr_name)
