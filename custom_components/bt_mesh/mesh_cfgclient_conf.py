"""mesh_cfgclient configuration file reader"""
from __future__ import annotations

import os.path, time
from pathlib import Path
import itertools
import json
from dataclasses import dataclass
from uuid import UUID

from . import BtMeshModelId

import logging
_LOGGER = logging.getLogger(__name__)



PATTERN_ELEMENTS: Final = "elements"
PATTERN_PRIORITY: Final = "priority"
PATTERN_MAIN: Final = "main"
PATTERN_TEMPERATURE: Final = "temperature"
PATTERN_HUE: Final = "hue"
PATTERN_SATURATION: Final = "saturation"

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
JSON_BIND: Final = "bind"
JSON_FEATURES: Final = "features"
JSON_RELAY: Final = "relay"
JSON_PROXY: Final = "proxy"
JSON_FRIEND: Final = "friend"
JSON_LOW_POWER: Final = "lowPower"



# for searching devices in a nodes
MeshNodePatterns: Final = {
    BtMeshModelId.GenericOnOffServer: {
        PATTERN_ELEMENTS: {
            PATTERN_MAIN: [
                BtMeshModelId.GenericOnOffServer
            ]
        },
        PATTERN_PRIORITY: 2
    },
    BtMeshModelId.GenericLevelServer: {
        PATTERN_ELEMENTS: {
            PATTERN_MAIN: [
                BtMeshModelId.GenericLevelServer
            ]
        },
        PATTERN_PRIORITY: 2
    },
    BtMeshModelId.GenericPowerOnOffSetupServer: {
        PATTERN_ELEMENTS: {
            PATTERN_MAIN: [
                BtMeshModelId.GenericPowerOnOffServer,
                BtMeshModelId.GenericPowerOnOffSetupServer
            ]
        },
        PATTERN_PRIORITY: 0
    },
    BtMeshModelId.GenericBatteryServer: {
        PATTERN_ELEMENTS: {
            PATTERN_MAIN: [
                BtMeshModelId.GenericBatteryServer
            ]
        },
        PATTERN_PRIORITY: 0
    },
    BtMeshModelId.LightLightnessSetupServer: {
        PATTERN_ELEMENTS: {
            PATTERN_MAIN: [
                BtMeshModelId.GenericOnOffServer,
                BtMeshModelId.GenericLevelServer,
                BtMeshModelId.LightLightnessServer,
                BtMeshModelId.LightLightnessSetupServer
            ]
        },
        PATTERN_PRIORITY: 1
    },
    BtMeshModelId.LightCTLSetupServer: {
        PATTERN_ELEMENTS: {
            PATTERN_MAIN: [
                BtMeshModelId.GenericOnOffServer,
                BtMeshModelId.GenericLevelServer,
                BtMeshModelId.LightLightnessServer,
                BtMeshModelId.LightLightnessSetupServer,
                BtMeshModelId.LightCTLServer,
                BtMeshModelId.LightCTLSetupServer
            ],
            PATTERN_TEMPERATURE: [
                BtMeshModelId.GenericLevelServer,
                BtMeshModelId.LightCTLTemperatureServer
            ]
        },
        PATTERN_PRIORITY: 0
    },
    BtMeshModelId.LightHSLSetupServer: {
        PATTERN_ELEMENTS: {
            PATTERN_MAIN: [
                BtMeshModelId.GenericOnOffServer,
                BtMeshModelId.GenericLevelServer,
                BtMeshModelId.LightLightnessServer,
                BtMeshModelId.LightLightnessSetupServer,
                BtMeshModelId.LightHSLServer,
                BtMeshModelId.LightHSLSetupServer
            ],
            PATTERN_HUE: [
                BtMeshModelId.GenericLevelServer,
                BtMeshModelId.LightHSLHueServer
            ],
            PATTERN_SATURATION: [
                BtMeshModelId.GenericLevelServer,
                BtMeshModelId.LightHSLSaturationServer
            ],
        },
        PATTERN_PRIORITY: 0
    },
    BtMeshModelId.SensorServer: {
        PATTERN_ELEMENTS: {
            PATTERN_MAIN: [
                BtMeshModelId.SensorServer
            ],
        },
        PATTERN_PRIORITY: 0
    },
    BtMeshModelId.ThermostatServer: {
        PATTERN_ELEMENTS: {
            PATTERN_MAIN: [
                BtMeshModelId.ThermostatServer
            ],
        },
        PATTERN_PRIORITY: 0
    },
}


@dataclass
class MeshCfgDevice:
    uuid: UUID
    cid: int
    pid: int
    vid: int
    unicast_addr: int
    relay: bool
    proxy: bool
    friend: bool
    low_power: bool


@dataclass
class MeshCfgModelExtend:
    name: str
    unicast_addr: int
    app_key: int


@dataclass
class MeshCfgModel:
    device: MeshCfgDevice
    model_id: BtMeshModelId
    unicast_addr: int
    app_key: int
    extends: dict[str, MeshCfgModelExtend]

    @property
    def name(self) -> str:
        return "%04x-%s" % (self.unicast_addr, BtMeshModelId.get_name(self.model_id))

    @property
    def unique_id(self) -> str:
        return "%04x-%04x-%s" % (self.unicast_addr, self.model_id, self.device_id)



class MeshCfgclientConf:
    @staticmethod
    def _match_models_pattern(pattern_models, models):
        # match models of single node element with
        # single template modles element

        models_match = dict()
        for model in models:
            try:
                model_id = int(model[JSON_MODEL_ID], 16)
                models_match[model_id] = False
            except Exception as e:
                pass

        num_models_match = 0
        for pattern_model in pattern_models:
            if pattern_model in models_match and models_match[pattern_model] is False:
                models_match[pattern_model] = True
                num_models_match += 1

        is_match = len(pattern_models) == num_models_match
        return is_match


    @staticmethod
    def _match_node_models(pattern_elements, elements):
        # find pattern in node elements

        if len(elements) < len(pattern_elements.keys()):
            return None

        elements_match = []
        for i in range(len(elements)):
            partial_elements = elements[i:]

            partial_elements_match = {}
            for (pattern_element_name, pattern_models) in pattern_elements.items():

                for element in partial_elements:
                    try:
                        element_idx = int(element[JSON_INDEX])
                        models = element[JSON_MODELS]
                        is_match = MeshCfgclientConf._match_models_pattern(pattern_models, models)
                        if is_match:
                            partial_elements_match[pattern_element_name] = element_idx
                            break
                    except Exception as e:
                        pass

            if len(pattern_elements.keys()) == len(partial_elements_match.keys()) and \
                    not partial_elements_match in elements_match:
                elements_match.append(partial_elements_match)

        return elements_match


    @staticmethod
    def _get_node_models(elements):
        # find all model in elements based on a pattern
        models_match = {}

        for pattern_model_id in MeshNodePatterns:
            pattern_elements = MeshNodePatterns[pattern_model_id][PATTERN_ELEMENTS]
            elements_match = MeshCfgclientConf._match_node_models(pattern_elements, elements)
            if elements_match:
                models_match[pattern_model_id] = elements_match

        return models_match

    @staticmethod
    def _clean_models_intersection(models):
        # remove intersecting models according to priority

        drop_list = list()
        result_models = dict()

        for (model_a, model_b) in list(itertools.combinations(models.keys(), 2)):
            model_a_priority = int(MeshNodePatterns[int(model_a)][PATTERN_PRIORITY])
            model_b_priority = int(MeshNodePatterns[int(model_b)][PATTERN_PRIORITY])
            elements_a = {idx: MeshNodePatterns[int(model_a)][PATTERN_ELEMENTS][name]
                for val in models[model_a]
                    for (name, idx) in val.items()}
            elements_b = {idx: MeshNodePatterns[int(model_b)][PATTERN_ELEMENTS][name]
                for val in models[model_b]
                    for (name, idx) in val.items()}

            for idx in elements_a.keys():
                if idx in elements_b:
                    intersection = set(elements_a[idx]).intersection(elements_b[idx])
                    if intersection:
                        if model_a_priority < model_b_priority:
                            drop_list.append((model_b, idx))
                        elif model_a_priority > model_b_priority:
                            drop_list.append((model_a, idx))

        # cleanup models list
        for model_id in models.keys():
            for element_item in models[model_id]:
                t = (model_id, element_item.values())
                is_drop_element = False
                for idx in element_item.values():
                    t = (model_id, idx)
                    if t in drop_list:
                        is_drop_element = True
                        break;

                # delete all elements of the model if there is
                # a conflict in at least one of them
                if not is_drop_element:
                    if model_id not in result_models:
                        result_models[model_id] = list()
                    result_models[model_id].append(element_item)

        return result_models


    @staticmethod
    def _parse(data, uuid = None):
        # get provisioners
        provisioners = [provisioner[JSON_UUID]
            for provisioner in data.get(JSON_PROVISIONERS, ())]

        # get own (client) appKeys
        app_keys = []
        if uuid is not None:
            app_keys = [int(node_app_key[JSON_INDEX])
                for node in data.get(JSON_NODES, ())
                    if JSON_UUID in node and node[JSON_UUID].lower() == uuid.lower()
                        for node_app_key in node.get(JSON_APP_KEYS, ())
                            if JSON_INDEX in node_app_key]

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
            except Exception as e:
                continue

            if JSON_FEATURES in node:
                node_features = node[JSON_FEATURES]
                node_relay = True if int(node_features.get(JSON_RELAY, 0)) > 0 else False
                node_proxy = True if int(node_features.get(JSON_PROXY, 0)) > 0 else False
                node_friend = True if int(node_features.get(JSON_FRIEND, 0)) > 0 else False
                node_low_power = True if int(node_features.get(JSON_LOW_POWER, 0)) > 0 else False
            else:
                node_relay = False
                node_proxy = False
                node_friend = False
                node_low_power = False

            # skip provisioners
            if node_uuid in provisioners:
                continue

            # get models from node and clean intersecting models
            models_match = MeshCfgclientConf._get_node_models(node_elements)
            models_match = MeshCfgclientConf._clean_models_intersection(models_match)
            if not models_match:
                continue

            # get models keys
            model_keys = {}
            for element in node_elements:
                try:
                    element_idx = int(element[JSON_INDEX])
                    element_models = element[JSON_MODELS]

                    for element_model in element_models:
                        try:
                            element_model_id = int(element_model[JSON_MODEL_ID], 16)
                            bind = element_model[JSON_BIND]

                            key = None
                            if not app_keys and bind:
                                key = int(bind[0])
                            else:
                                for bind_key in bind:
                                    if int(bind_key) in app_keys:
                                        key = int(bind_key)
                                        break

                            if key is not None:
                                if element_idx not in model_keys:
                                    model_keys[element_idx] = {}
                                model_keys[element_idx][element_model_id] = key

                        except Exception as e:
                            pass

                except Exception as e:
                    pass

            device_info = {
                JSON_UUID: node_uuid,
                JSON_UNICAST_ADDRESS: node_unicast_addr,
                JSON_CID: node_cid,
                JSON_PID: node_pid,
                JSON_VID: node_vid,
                JSON_MODELS: models_match,
                JSON_APP_KEYS: model_keys,
                JSON_RELAY: node_relay,
                JSON_PROXY: node_proxy,
                JSON_FRIEND: node_friend,
                JSON_LOW_POWER: node_low_power,
            }
            devices.append(device_info)

        return devices

    devices: list

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

    def load(self) -> dict:
        conf_file = Path(self.filename)
        conf_data = json.loads(conf_file.read_text(encoding="utf8"))
        self.devices = self._parse(conf_data)
        return self.devices

    def get_devices(self) -> list:
        cfg_devices = list()
        for device_item in self.devices:
            device_id = device_item[JSON_UUID]
            device_unicast_addr = device_item[JSON_UNICAST_ADDRESS]
            cfg_devices.append(
                MeshCfgDevice(
                    uuid=UUID(device_id),
                    cid=device_item[JSON_CID],
                    pid=device_item[JSON_PID],
                    vid=device_item[JSON_VID],
                    unicast_addr=device_unicast_addr,
                    relay=device_item[JSON_RELAY],
                    proxy=device_item[JSON_PROXY],
                    friend=device_item[JSON_FRIEND],
                    low_power=device_item[JSON_LOW_POWER],
                )
            )
        return cfg_devices


    def get_models(self) -> list:
        models = []
        for device_item in self.devices:
            device_id = device_item[JSON_UUID]
            device_unicast_addr = device_item[JSON_UNICAST_ADDRESS]
            cfg_device = MeshCfgDevice(
                uuid=UUID(device_id),
                cid=device_item[JSON_CID],
                pid=device_item[JSON_PID],
                vid=device_item[JSON_VID],
                unicast_addr=device_unicast_addr,
                relay=device_item[JSON_RELAY],
                proxy=device_item[JSON_PROXY],
                friend=device_item[JSON_FRIEND],
                low_power=device_item[JSON_LOW_POWER],
            )

            for model_items_id, model_items in device_item[JSON_MODELS].items():
                for element_item in model_items:
                    extends = {key: MeshCfgModelExtend(
                        name=key,
                        unicast_addr=device_unicast_addr+val,
                        app_key=device_item[JSON_APP_KEYS][val][model_items_id]
                            if val in device_item[JSON_APP_KEYS]
                                and model_items_id in device_item[JSON_APP_KEYS][val] else None
                    ) for key, val in element_item.items()}

                    if extends[PATTERN_MAIN].app_key is not None:
                        mesh_cfg_model = MeshCfgModel(
                            device=cfg_device,
                            model_id=model_items_id,
                            unicast_addr=extends[PATTERN_MAIN].unicast_addr,
                            app_key=extends[PATTERN_MAIN].app_key,
                            extends={key: val for key, val in extends.items()
                                if key != PATTERN_MAIN and val.app_key is not None}
                        )

                        models.append(mesh_cfg_model)

        return models


    def get_models_by_model_id(self, model_id: BtMeshModelId) -> list:
        return [model for model in self.get_models() if  model.model_id == model_id]
