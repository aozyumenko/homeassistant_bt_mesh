"""mesh_cfgclient configuration file reader"""
from __future__ import annotations

import os.path, time
import json

from .bt_mesh import BtMeshApplication, BtMeshModelId

import logging
_LOGGER = logging.getLogger(__name__)



ELEMENT_MAIN: Final = "main"
ELEMENT_TEMPERATURE: Final = "temperature"
ELEMENT_HUE: Final = "hue"
ELEMENT_SATURATION: Final = "saturation"

JSON_PROVISIONERS: Final = "provisioners"
JSON_NODES: Final = "nodes"
JSON_UUID: Final = "UUID"
JSON_UNICAST_ADDRESS: Final = "unicastAddress"
JSON_ELEMENTS: Final = "elements"
JSON_CID: Final = "cid"
JSON_PID: Final = "pid"
JSON_VID: Final = "vid"
JSON_APP_KEYS: Final = "appKeys"
JSON_INDEX: Final = "index"
JSON_MODELS: Final = "models"
JSON_MODEL_ID: Final = "modelId"



# for searching devices in a nodes
MeshNodePatterns: Final = {
    BtMeshModelId.GenericOnOffServer: {
        ELEMENT_MAIN: [
            BtMeshModelId.GenericOnOffServer
        ]
    },
    BtMeshModelId.GenericPowerOnOffSetupServer: {
        ELEMENT_MAIN: [
            BtMeshModelId.GenericPowerOnOffServer,
            BtMeshModelId.GenericPowerOnOffSetupServer
        ]
    },
    BtMeshModelId.LightLightnessSetupServer: {
        ELEMENT_MAIN: [
            BtMeshModelId.GenericOnOffServer,
            BtMeshModelId.LightLightnessServer,
            BtMeshModelId.LightLightnessSetupServer
        ]
    },
    BtMeshModelId.LightCTLSetupServer: {
        ELEMENT_MAIN: [
            BtMeshModelId.GenericOnOffServer,
            BtMeshModelId.LightLightnessServer,
            BtMeshModelId.LightLightnessSetupServer,
            BtMeshModelId.LightCTLServer,
            BtMeshModelId.LightCTLSetupServer
        ],
        ELEMENT_TEMPERATURE: [
            BtMeshModelId.LightCTLTemperatureServer
        ]
    },
    BtMeshModelId.LightHSLSetupServer: {
        ELEMENT_MAIN: [
            BtMeshModelId.GenericOnOffServer,
            BtMeshModelId.LightLightnessServer,
            BtMeshModelId.LightLightnessSetupServer,
            BtMeshModelId.LightHSLServer,
            BtMeshModelId.LightHSLSetupServer
        ],
        ELEMENT_HUE: [
            BtMeshModelId.LightHSLHueServer
        ],
        ELEMENT_SATURATION: [
            BtMeshModelId.LightHSLSaturationServer
        ],
    },
    BtMeshModelId.SensorServer: {
        ELEMENT_MAIN: [
            BtMeshModelId.SensorServer
        ],
    }
}



class MeshCfgclientConf:
    @staticmethod
    def _match_models_pattern(pattern_models, models):
        models_match = {}
        num_models_match = 0

        for model in models:
            try:
                model_id = int(model[JSON_MODEL_ID], 16)
            except KeyError:
                return False
            models_match[model_id] = False

        for pattern_model in pattern_models:
            if pattern_model in models_match and models_match[pattern_model] is False:
                models_match[pattern_model] = True
                num_models_match += 1

        is_match = len(pattern_models) == num_models_match
        return is_match


    @staticmethod
    def _match_node_models(pattern_elements, elements):
        if len(elements) < len(pattern_elements.keys()):
            return None

        elements_match = []

        for i in range(len(elements)):
            partial_elements = elements[i:]

            partial_elements_match = {}
            for pattern_element_name in pattern_elements.keys():
                pattern_models = pattern_elements[pattern_element_name]

                for element in partial_elements:
                    try:
                        element_idx = int(element[JSON_INDEX])
                        models = element[JSON_MODELS]
                    except KeyError:
                        continue
                    is_match = MeshCfgclientConf._match_models_pattern(pattern_models, models)

                    if is_match:
                        partial_elements_match[pattern_element_name] = element_idx
                        break

            if len(pattern_elements.keys()) == len(partial_elements_match.keys()) and not partial_elements_match in elements_match:
                elements_match.append(partial_elements_match)

        return elements_match if len(elements_match) > 0 else None


    @staticmethod
    def _get_node_models(elements):
        models_match = {}

        for pattern_model_id in MeshNodePatterns:
            pattern_elements = MeshNodePatterns[pattern_model_id]

            elements_match = MeshCfgclientConf._match_node_models(pattern_elements, elements)
            if elements_match is not None:
                models_match[pattern_model_id] = elements_match

        return models_match if len(models_match.keys()) > 0 else None


    @staticmethod
    def _parse(data, uuid = None):
        # get provisioners
        provisioners = list()
        for provisioner in data.get(JSON_PROVISIONERS, ()):
            provisioners.append(provisioner[JSON_UUID])

        # get own (client) keys
        if uuid is not None:
            app_keys = []
            for node in data.get(JSON_NODES, ()):
                try:
                    node_uuid = node[JSON_UUID]
                except KeyError:
                    continue

                if node_uuid.lower() == uuid.lower():
                    for node_app_key in node.get(JSON_APP_KEYS, ()):
                        if JSON_INDEX in node_app_key:
                            app_keys.append(int(node_app_key[JSON_INDEX]))
                    break;
        else:
            app_keys = None

        # enumerate nodes
        devices = []
        for node in data.get(JSON_NODES, ()):
            try:
                node_uuid = node[JSON_UUID]
                node_unicast_addr = int(node[JSON_UNICAST_ADDRESS], 16)
                node_elements = node[JSON_ELEMENTS]
                node_cid = int(node[JSON_CID], 16)
                node_pid = int(node[JSON_PID], 16)
                node_vid = int(node[JSON_VID], 16)
            except KeyError:
                continue

            # skip provisioners
            if node_uuid in provisioners:
                continue

            # get models from node
            models_match = MeshCfgclientConf._get_node_models(node_elements)
            if models_match is None:
                continue

            # get models keys
            model_keys = {}
            for element in node_elements:
                element_idx = int(element[JSON_INDEX])
                models = element['models']

                for model in models:
                    model_id = int(model['modelId'], 16)
                    bind = model['bind']

                    key = None
                    if app_keys is None and len(bind) > 0:
                        key = int(bind[0])
                    else:
                        for bind_key in bind:
                            if int(bind_key) in app_keys:
                                key = int(bind_key)
                                break
                    if key is not None:
                        if element_idx not in model_keys:
                            model_keys[element_idx] = {}
                        model_keys[element_idx][model_id] = key

            device_info = {
                'UUID': node_uuid,
                'unicastAddress': node_unicast_addr,
                'cid': node_cid,
                'pid': node_pid,
                'vid': node_vid,
                'models': models_match,
                'app_keys': model_keys
            }
            devices.append(device_info)

        return devices


    def __init__(self, filename: str):
        self.last_mtime = None
        self.filename: str = os.path.expanduser(filename)
        self.devices = ()

    def is_modified(self):
        try:
            cur_mtime = os.path.getmtime(self.filename)
            if self.last_mtime is None or self.last_mtime < cur_mtime:
                result = True
            else:
                result = False
            self.last_mtime = cur_mtime
            return result
        except Exception:
            _LOGGER.error("Failed to get file %s modification time" % (self.filename))
            return False

    def load(self):
        # FIXME: self.devices should be defined in any case
        with open(self.filename) as meshcfg_file:
            data = json.load(meshcfg_file)
            self.devices = self._parse(data)
