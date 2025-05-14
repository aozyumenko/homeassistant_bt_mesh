from enum import IntEnum

from bluetooth_mesh.messages.properties import PropertyID
from bluetooth_mesh.models.generic.onoff import GenericOnOffServer
from bluetooth_mesh.models.generic.ponoff import GenericPowerOnOffServer, GenericPowerOnOffSetupServer
from bluetooth_mesh.models.generic.battery import GenericBatteryServer
from bluetooth_mesh.models.sensor import SensorServer, SensorSetupServer, SensorClient
from bluetooth_mesh.models.light.lightness import LightLightnessServer, LightLightnessSetupServer
from bluetooth_mesh.models.light.ctl import LightCTLServer, LightCTLSetupServer, LightCTLTemperatureServer
from bluetooth_mesh.models.light.hsl import LightHSLServer, LightHSLSetupServer, LightHSLHueServer, LightHSLSaturationServer
from bluetooth_mesh.models.vendor.thermostat import ThermostatServer


class IntEnumName(IntEnum):
    @classmethod
    def has_value(_class, val: int):
        return val in _class._value2member_map_

    @classmethod
    def get_name(_class, val: int):
        return _class(val).name if _class.has_value(val) else "%04x" % (val)

def model_id_to_num(model_id):
    return (0 if model_id[0] is None else model_id[0] * 65536) + model_id[1]


class BtMeshModelId(IntEnumName):
    """ BT Mesh model names. """
    GenericOnOffServer = model_id_to_num(GenericOnOffServer.MODEL_ID)
    GenericPowerOnOffServer = model_id_to_num(GenericPowerOnOffServer.MODEL_ID)
    GenericPowerOnOffSetupServer = model_id_to_num(GenericPowerOnOffSetupServer.MODEL_ID)
    GenericBatteryServer = model_id_to_num(GenericBatteryServer.MODEL_ID)
    SensorServer =  model_id_to_num(SensorServer.MODEL_ID),
    SensorSetupServer = model_id_to_num(SensorSetupServer.MODEL_ID),
    SensorClient = model_id_to_num(SensorClient.MODEL_ID),
    LightLightnessServer = model_id_to_num(LightLightnessServer.MODEL_ID)
    LightLightnessSetupServer = model_id_to_num(LightLightnessSetupServer.MODEL_ID)
    LightCTLServer = model_id_to_num(LightCTLServer.MODEL_ID)
    LightCTLSetupServer = model_id_to_num(LightCTLSetupServer.MODEL_ID)
    LightCTLTemperatureServer = model_id_to_num(LightCTLTemperatureServer.MODEL_ID)
    LightHSLServer = model_id_to_num(LightHSLServer.MODEL_ID)
    LightHSLSetupServer = model_id_to_num(LightHSLSetupServer.MODEL_ID)
    LightHSLHueServer = model_id_to_num(LightHSLHueServer.MODEL_ID)
    LightHSLSaturationServer = model_id_to_num(LightHSLSaturationServer.MODEL_ID)
    ThermostatServer = model_id_to_num(ThermostatServer.MODEL_ID)

class BtSensorAttrPropertyId(IntEnumName):
    """ BT Mesh sensor property names. """
    PRECISE_TOTAL_DEVICE_ENERGY_USE = PropertyID.PRECISE_TOTAL_DEVICE_ENERGY_USE
    PRESENT_DEVICE_INPUT_POWER = PropertyID.PRESENT_DEVICE_INPUT_POWER
    PRESENT_INPUT_CURRENT = PropertyID.PRESENT_INPUT_CURRENT
    PRESENT_INPUT_VOLTAGE = PropertyID.PRESENT_INPUT_VOLTAGE
