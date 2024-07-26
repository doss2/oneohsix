"""Handles generation of IRIG 106 Chapter 11 packets"""

import struct
from array import array
from typing import Literal


def int_to_uint48_bytes(n: int, order: Literal["little", "big"] = "little"):
    if not (0 <= n < 2**48):
        raise ValueError("Integer out of range for uint48")
    return n.to_bytes(6, byteorder=order)


class CH11_Packet:
    def __init__(
        self,
        channel_id: int,
        sequence_number: int,
        data_type: int,
        rtc: int,
        data: bytes,
    ) -> None:
        self.sync_pattern = struct.pack("<H", 60197)
        self.channel_id = struct.pack("<H", channel_id)
        self.sequence_number = struct.pack("<B", sequence_number)
        self.data_type = data_type
        self.rtc = rtc.to_bytes(6, "little")
        self.packet_flags = struct.pack("<B", 2)
        self.data = data
        self.packet: bytes = b""

        self.packet_length = struct.pack("<I", 24 + len(data) + 2)
        self.data_length = struct.pack("<I", len(data))

        self.data_type_ver = b"0x00"
        self.set_data_type_version()

        self.data_checksum = struct.pack("<H", self.calculate_checksum(self.data))
        self._set_packet()

    def set_data_type_version(self) -> None:
        if self.data_type == 105:
            self.data_type_ver = struct.pack("<B", 6)
            self.data_type = struct.pack("<B", self.data_type)
        elif self.data_type == 18:
            self.data_type_ver = struct.pack("<B", 8)
            self.data_type = struct.pack("<B", self.data_type)
        elif self.data_type == 17:
            self.data_type_ver = struct.pack("<B", 6)
            self.data_type = struct.pack("<B", self.data_type)
        else:
            raise NotImplementedError

    def _set_packet(self) -> None:
        header_no_chksum = (
            self.sync_pattern
            + self.channel_id
            + self.packet_length
            + self.data_length
            + self.data_type_ver
            + self.sequence_number
            + self.packet_flags
            + self.data_type
            + self.rtc
        )
        header_checksum = struct.pack("<H", self.calculate_checksum(header_no_chksum))

        self.packet = (
            header_no_chksum + header_checksum + self.data + self.data_checksum
        )

    @staticmethod
    def calculate_checksum(data: bytes) -> int:
        # # Ensure data length is even
        # if len(data) % 2 != 0:
        #     data += b"\x00"

        # checksum: int = 0
        # # Sum all 16-bit words
        # for i in range(0, len(data), 2):
        #     word = (data[i] << 8) + data[i + 1]
        #     checksum += word
        #     # Wrap around the carry if it overflows 16 bits
        #     checksum = (checksum & 0xFFFF) + (checksum >> 16)

        # # Final wrap around
        # checksum = (checksum & 0xFFFF) + (checksum >> 16)
        # # One's complement
        # checksum = ~checksum & 0xFFFF

        checksum = sum(array("H", data)[:-1]) & 0xFFFF
        return checksum
