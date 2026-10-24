"""Synthetic AN3155 peer. All identity bytes are invented in memory for tests."""
from pathlib import Path
import struct

from h60_common import ACK, NACK, FLASH_BASE, FLASH_BYTES, SIGNATURE_BASE, xor


def identity():
    return {"schema": "h60.rom-identity.v1", "pid": 0x0413,
            "uid_hex": bytes(range(1, 13)).hex(), "flash_size_kib": 512,
            "board_revision_operator_asserted": "V3.7", "base": FLASH_BASE}


def flash_image():
    data = bytearray((n * 37 + 11) % 256 for n in range(FLASH_BYTES))
    struct.pack_into("<II", data, 0, 0x20020000, FLASH_BASE + 9)
    return bytes(data)


def hex_image(data):
    def record(address, kind, payload):
        raw = bytes((len(payload),)) + address.to_bytes(2, "big") + bytes((kind,)) + payload
        return ":" + (raw + bytes((-sum(raw) & 255,))).hex().upper()
    lines = [record(0, 4, b"\x08\x00")]
    lines.extend(record(offset, 0, data[offset:offset + 64]) for offset in range(0, len(data), 64))
    return ("\n".join(lines + [record(0, 1, b"")]) + "\n").encode()


class FakeSerial:
    def __init__(self, flash=None, *, wrong_uid=False, erase_nack=False, corrupt_tail=False):
        self.flash = bytearray(flash if flash is not None else flash_image())
        self.buffer, self.phase, self.address = bytearray(), "command", None
        self.commands, self.writes, self.erase_packets, self.lines, self.all_writes = [], [], [], [], []
        self.wrong_uid, self.erase_nack, self.corrupt_tail = wrong_uid, erase_nack, corrupt_tail
        self.closed, self.is_open, self.open_settings = False, False, None
        self.dtr, self.rts = None, None

    def factory(self, **options):
        self.open_settings = options
        return self

    def open(self):
        self.is_open = True
        self.lines.append(("open", self.dtr, self.rts))

    def close(self):
        self.closed, self.is_open = True, False

    def reset_input_buffer(self):
        self.buffer.clear()

    def reset_output_buffer(self):
        pass

    def flush(self):
        pass

    def read(self, count):
        block = bytes(self.buffer[:count])
        del self.buffer[:count]
        return block

    def write(self, packet):
        packet = bytes(packet)
        self.all_writes.append(packet)
        if self.phase == "command":
            if packet == b"\x7f":
                self.buffer.append(ACK)
            else:
                assert len(packet) == 2 and packet[0] ^ packet[1] == 255
                command = packet[0]
                self.commands.append(command)
                assert command in (0, 2, 0x11, 0x31, 0x44), f"Unexpected mutation/GO: {command:#x}"
                self.buffer.append(ACK)
                if command == 0:
                    payload = bytes((0x31, 0, 2, 0x11, 0x31, 0x44))
                    self.buffer.extend(bytes((len(payload) - 1,)) + payload + bytes((ACK,)))
                elif command == 2:
                    self.buffer.extend(b"\x01\x04\x13" + bytes((ACK,)))
                else:
                    self.phase = {0x11: "read-address", 0x31: "write-address", 0x44: "erase"}[command]
        elif self.phase.endswith("address"):
            assert len(packet) == 5 and xor(packet) == 0
            self.address = int.from_bytes(packet[:4], "big")
            self.phase = self.phase.replace("address", "data")
            self.buffer.append(ACK)
        elif self.phase == "read-data":
            assert len(packet) == 2 and xor(packet) == 255
            count = packet[0] + 1
            if self.address == SIGNATURE_BASE:
                signature = bytearray(256)
                signature[0x10:0x1c] = bytes(range(2, 14)) if self.wrong_uid else bytes(range(1, 13))
                signature[0x22:0x24] = (512).to_bytes(2, "little")
                data = signature[:count]
            else:
                offset = self.address - FLASH_BASE
                assert 0 <= offset < len(self.flash) and offset + count <= len(self.flash)
                data = bytearray(self.flash[offset:offset + count])
                if self.corrupt_tail and self.writes and offset == 32768:
                    data[0] ^= 1
            self.buffer.extend(bytes((ACK,)) + data)
            self.phase = "command"
        elif self.phase == "write-data":
            count = packet[0] + 1
            assert len(packet) == count + 2 and xor(packet) == 0
            offset = self.address - FLASH_BASE
            assert 0 <= offset and offset + count <= 16384
            self.writes.append((self.address, count))
            self.flash[offset:offset + count] = packet[1:-1]
            self.buffer.append(ACK)
            self.phase = "command"
        elif self.phase == "erase":
            assert packet == bytes(5), "Only sector zero may be erased."
            self.erase_packets.append(packet)
            if not self.erase_nack:
                self.flash[:16384] = b"\xff" * 16384
            self.buffer.append(NACK if self.erase_nack else ACK)
            self.phase = "command"
        else:
            raise AssertionError(self.phase)
        return len(packet)
