"""Module with known BT Mesh device IDs."""
from __future__ import annotations

from typing import Dict
from bluetooth_numbers.exceptions import (
    BluetoothNumbersError,
    No16BitIntegerError,
)

__all__ = ["product"]


class UnknownPIDError(BluetoothNumbersError):
    """Exception raised when a PID is not known."""


class PIDDict(Dict[int, str]):
    def __missing__(self, key: int) -> str:
        """Try the key and raise exception when it's invalid.

        Args:
            key (int): The key to check.

        Raises:
            No16BitIntegerError: If ``key`` isn't a 16-bit unsigned integer.
            UnknownPIDError: If ``key`` isn't in this PIDDict instance.
        """
        if is_uint16(key):
            raise UnknownPIDError(key)

        raise No16BitIntegerError(key)


product = PIDDict(
    {  # 16-bit Product IDs
        0x5301: "SCG Mesh Wall Switch 1",
        0x5302: "SCG Mesh Wall Switch 2",
        0x5303: "SCG Mesh Wall Switch 3",
        0x5304: "SCG Mesh Wall Plug",
        0x5305: "SCG RGBWC LED Light Model 1",
        0x5306: "SCG RGBW LED Light Model 1",
        0x5307: "Smart Meter HIKING DDS328-2",
        0x5308: "Thermostat K5H16A-wifi",
        0x5309: "SCG Mesh Wall Plug PM",
        0x530a: "Temperatute & Humidity Sensor TH01",
        0x530b: "SCG Screen Controller",
        0x530c: "Radiator Thermostat BRT-100",
    }
)
