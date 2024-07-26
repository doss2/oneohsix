import threading
import time
import datetime as dt
import socket
import struct

import numpy as np
from oneohsix.c11 import CH11_Packet, int_to_uint48_bytes


def to_uint4(value):
    """Convert an integer to a 4-bit unsigned integer."""
    return value & 0xF


# Packing two uint4 values into a byte
def pack_uint4(high, low):
    """Pack two 4-bit unsigned integers into one byte."""
    high = to_uint4(high)
    low = to_uint4(low)
    return (high << 4) | low


def to_uint14(value):
    """Convert an integer to a 24-bit unsigned integer and return it as a byte array."""
    if value < 0 or value >= 2**14:
        raise ValueError("Value must be between 0 and 2^14-1 (inclusive).")

    # Pack into 2 bytes (little-endian)
    byte_array = value.to_bytes(2, "little")
    return byte_array


def to_uint24(value):
    """Convert an integer to a 24-bit unsigned integer and return it as a byte array."""
    if value < 0 or value > 0xFFFFFF:
        raise ValueError("Value must be between 0 and 2^24-1 (inclusive).")

    # Mask the value to ensure it's within 24 bits
    uint24_value = value & 0xFFFFFF

    # Pack into 3 bytes (big-endian)
    byte_array = uint24_value.to_bytes(3, "little")
    return byte_array


# Sine wave generator thread
class SineWaveGenerator(threading.Thread):
    def __init__(self, frequency, sample_rate, amplitude):
        threading.Thread.__init__(self)
        self.frequency = frequency
        self.sample_rate = sample_rate
        self.amplitude = amplitude
        self.running = True
        self.data = []

    def run(self):
        t = 0
        while self.running:
            t += 1 / self.sample_rate
            value = self.amplitude * np.sin(2 * np.pi * self.frequency * t)
            self.data.append(value)
            time.sleep(1 / self.sample_rate)

    def stop(self):
        self.running = False


# UDP sender thread
class UDPSender(threading.Thread):
    def __init__(self, host, mcst, port, sine_wave_generator):
        threading.Thread.__init__(self)
        self.start_time = time.time()
        self.rtc = (time.time() - self.start_time) * 10000000  #### Time 01
        self.host = host
        self.mcst = mcst
        self.port = port
        self.sine_wave_generator = sine_wave_generator
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.bind((self.host, 0))
        self.sequence_count = 0
        self.time_count = 0
        self.udp_count = 0
        self.iena_count = 0

        self.time_secs = 0
        self.time_nanos = 0

        self.wrap_in_ch11 = False
        self.wrap_in_ch11 = True
        self.iena = True

    def _set_rtc(self) -> None:
        self.rtc = (time.time() - self.start_time) * 10000000

    def run(self):
        count = 0
        last_time = int(time.time())
        while self.sine_wave_generator.running:
            time.sleep(1 / pkt_frequency)
            curr_time = int(time.time())
            self._set_rtc()  #### Time 02
            if self.sine_wave_generator.data:
                # Generate payloads with padding and send
                payload = struct.pack("!f", self.sine_wave_generator.data[-1])

                if self.iena:
                    header = self.set_iena_header()
                    msg = header + payload
                    msg += struct.pack("!H", 0xDEAD)

                else:
                    header = self.set_inetx_header()
                    msg = header + payload

                if not self.wrap_in_ch11:
                    self.sock.sendto(msg, (self.mcst, self.port))
                    continue
                time.sleep(0.2)
                self._set_rtc()
                msg = self.eth_f0_header_wrapper(data=msg)

                # filler = bytes.fromhex(
                #     "01005E00000AF4EE08BB7AE708004500003CEA0900000111075FC0A81C96EB00000AC8020FA00028826A"
                # )
                packet = self.udp_header(21) + self.ch11_wrapper(msg)
                self.sock.sendto(packet, (self.mcst, self.port))

                if curr_time > last_time:
                    # time_packet = padding + self.time_packet()
                    time_packet = self.udp_header(1) + self.time_packet()
                    self.sock.sendto(time_packet, (self.mcst, self.port))
                    print(f"Sent data: {self.sine_wave_generator.data[-1]}")
                    last_time = curr_time

    def udp_header(self, channel_id: int) -> bytes:
        udp_header = to_uint24(self.udp_count)
        udp_header += struct.pack("<B", 23)
        # udp_header += struct.pack("<H", channel_id)
        # udp_header += struct.pack("<HHH", 0, 0, 0)

        if self.udp_count <= 16777214:
            self.udp_count += 1
        else:
            self.udp_count = 0

        return udp_header

    def time_packet(self) -> bytes:
        # secs, nanos = self.get_time_since_epoch()

        # CSDW = 0000 0000 0000 0000 0100 0001 0100 0001
        # ITS = GPS, DATE = M&Y avail & LY, FMT = 0x4, SRC = 0x1
        # TODO: Try GPS if NTP doesn't work

        now_time = time.time()
        csdw = struct.pack("<BBBB", 65, 3, 0, 0)  # TODO: this is different
        t = dt.datetime.now()

        ms = t.microsecond // 1000
        Hmn = ms // 100
        Tmn = (ms - (Hmn * 100)) // 10

        TSn = t.second // 10
        Sn = t.second - (TSn * 10)
        TMn = t.minute // 10
        Mn = t.minute - (TMn * 10)
        THn = t.hour // 10
        Hn = t.hour - (THn * 10)

        # Month and year format

        day = t.day
        TDn = day // 10
        day -= TDn * 10
        Dn = day

        month = t.month
        TOn = month // 10
        month -= TOn * 10
        On = month

        year = t.year
        OYn = year // 1000
        year -= OYn * 1000
        HYn = year // 100
        year -= HYn * 100
        TYn = year // 10
        year -= TYn * 10
        Yn = year

        body = struct.pack(
            "<BBBBBBBB",
            pack_uint4(Hmn, Tmn),
            pack_uint4(TSn, Sn),
            pack_uint4(TMn, Mn),
            pack_uint4(THn, Hn),
            pack_uint4(TDn, Dn),
            pack_uint4(TOn, On),
            pack_uint4(TYn, Yn),
            pack_uint4(OYn, HYn),
        )

        data = csdw + body
        pkt = CH11_Packet(
            channel_id=1,
            sequence_number=self.time_count,
            data_type=17,
            rtc=int(self.rtc),
            data=data,
        ).packet

        if self.time_count <= 254:
            self.time_count += 1
        else:
            self.time_count = 0
        return pkt

    def set_inetx_header(self) -> bytes:
        self.time_secs, self.time_nanos = self.get_time_since_epoch()
        preamble = struct.pack("!I", 0x11000000)
        stream_id = struct.pack("!I", 0xD000)
        sequence = struct.pack("!I", self.sequence_count)
        pkt_len = struct.pack("!I", 32)  # 28 byte header + 4 byte payload
        # ptps, ptpn = self.get_time_since_epoch()
        payld_info = struct.pack("!I", 0)

        header = (
            preamble
            + stream_id
            + sequence
            + pkt_len
            + self.time_secs
            + self.time_nanos
            + payld_info
        )

        if self.sequence_count <= 254:
            self.sequence_count += 1
        else:
            self.sequence_count = 0

        return header

    def set_iena_header(self) -> bytes:
        header = struct.pack("!HH", 0xD000, 20)  # 16 byte header + 4 byte payload
        header += self.micros_since_new_year().to_bytes(6, "big")
        header += struct.pack("!H", 0)
        header += struct.pack("!H", self.iena_count)

        if self.iena_count < 65535:
            self.iena_count += 1
        else:
            self.iena_count = 0

        return header

    def eth_f0_header_wrapper(self, data: bytes) -> bytes:
        eth_header = struct.pack("<I", 1)  # CSDW
        eth_header += int(self.rtc).to_bytes(8, "little")
        # eth_header += struct.pack("<H", 0)  # Filler
        # eth_header += struct.pack("<IIIIIIII", 0,0,0,0,0,0,0,0)

        # eth_header += self.time_nanos
        # eth_header += self.time_secs

        filler = bytes(42)

        filler = bytes.fromhex(
            "01005E00000AF4EE08BB7AE708004500003CEA0900000111075FC0A81C96EB00000AC8020FA00028826A"
        )
        eth_header += to_uint14(len(data) + len(filler))
        eth_header += struct.pack(">H", 0)

        return eth_header + filler + data

    @staticmethod
    def micros_since_new_year() -> int:
        curr_time = dt.datetime.now()
        micros = (
            curr_time
            - dt.datetime(
                year=curr_time.year,
                month=1,
                day=1,
            )
        ).total_seconds() - 27
        micros = int(micros * 1000000)  # - 1800000000
        return micros

    @staticmethod
    def get_time_since_epoch():
        # Get the current time in seconds since the epoch
        current_time = time.time()

        # Separate the integer part and the fractional part
        seconds_since_epoch, fractional_part = divmod(current_time, 1)
        # seconds_since_epoch += 170

        # Convert to uint32
        seconds_since_epoch_uint32 = struct.pack(
            "!I", int(seconds_since_epoch) & 0xFFFFFFFF
        )

        # Convert the fractional part to nanoseconds and to uint32
        nanoseconds_since_second = struct.pack(
            "!I", int(fractional_part * 1e9) & 0xFFFFFFFF
        )

        return seconds_since_epoch_uint32, nanoseconds_since_second

    def ch11_wrapper(self, data):
        pkt = CH11_Packet(
            channel_id=21,
            sequence_number=self.sequence_count,
            data_type=105,
            rtc=int(self.rtc),
            data=data,
        ).packet

        return pkt


if __name__ == "__main__":
    # Configuration
    frequency = 1  # 1 Hz
    sample_rate = 100  # 100 samples per second
    amplitude = 1  # Amplitude of the sine wave

    host = "192.168.28.150"  # Localhost
    # host = "128.207.70.61"  # Localhost
    mcst = "235.0.0.10"
    port = 4000  # Arbitrary port
    pkt_frequency = 1

    # Create sine wave generator and UDP sender
    sine_wave_generator = SineWaveGenerator(frequency, sample_rate, amplitude)
    udp_sender = UDPSender(host, mcst, port, sine_wave_generator)

    # Start the threads
    sine_wave_generator.start()
    udp_sender.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping...")
        sine_wave_generator.stop()
        sine_wave_generator.join()
        udp_sender.join()
        print("Stopped")
