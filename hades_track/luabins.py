"""Reader for the luabins serialization used inside Hades II save files.

Format (from jakobhellermann/hades2-tools, which follows TannerRogalsky/luabins):
  u8 count of top level values
  value := u8 tag, payload
    '-' nil
    '0' false
    '1' true
    'N' f64 le
    'S' u32 len + utf8 bytes
    'T' u32 array_size, u32 hash_size, then (array_size+hash_size) key/value pairs
"""

from __future__ import annotations

import struct


class LuaError(ValueError):
    pass


class LuaTable(dict):
    """A decoded Lua table. Array part is keyed 1..n, hash part by its key."""


class _Reader:
    __slots__ = ("buf", "pos")

    def __init__(self, buf: bytes):
        self.buf = buf
        self.pos = 0

    def take(self, n: int) -> bytes:
        end = self.pos + n
        if end > len(self.buf):
            raise LuaError(f"unexpected end of data at {self.pos}")
        out = self.buf[self.pos:end]
        self.pos = end
        return out

    def u8(self) -> int:
        return self.take(1)[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def f64(self) -> float:
        return struct.unpack("<d", self.take(8))[0]

    def string(self) -> str:
        return self.take(self.u32()).decode("utf-8", "replace")

    def value(self):
        tag = self.u8()
        if tag == 0x2D:  # '-'
            return None
        if tag == 0x30:  # '0'
            return False
        if tag == 0x31:  # '1'
            return True
        if tag == 0x4E:  # 'N'
            return self.f64()
        if tag == 0x53:  # 'S'
            return self.string()
        if tag == 0x54:  # 'T'
            array_size = self.u32()
            hash_size = self.u32()
            table = LuaTable()
            for _ in range(array_size + hash_size):
                key = self.value()
                table[key] = self.value()
            return table
        raise LuaError(f"unknown value tag {tag!r} at {self.pos - 1}")


def loads(data: bytes):
    """Decode a luabins blob into a list of Python values."""
    r = _Reader(data)
    count = r.u8()
    if count > 250:
        raise LuaError(f"bad top level count {count}")
    values = [r.value() for _ in range(count)]
    if r.pos != len(data):
        raise LuaError(f"{len(data) - r.pos} trailing bytes")
    return values
