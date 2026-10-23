"""Hades II (SGB1) save file parser.

Layout reverse engineered by https://github.com/jakobhellermann/hades2-tools:
  "SGB1" | u32 adler32(rest) | u16 version | u16 version_unk | u64 timestamp
  | str location | u32 runs | u32 meta_points | u32 shrine_points | u32 grasp
  | u8 easy | u8 hard | [u32 unknown if version >= 18]
  | u32 n, n * str lua_keys | str current_map | str start_next_map
  | u32 lz4_len | lz4 block (decompresses to 15,679,488 bytes of luabins)
"""

from __future__ import annotations

import pathlib
import struct
import zlib

import lz4.block

from . import luabins

MAGIC = b"SGB1"
DECOMPRESSED_LEN = 15_679_488


class SaveError(ValueError):
    pass


class _Cursor:
    def __init__(self, buf: bytes, pos: int = 0):
        self.buf = buf
        self.pos = pos

    def take(self, n: int) -> bytes:
        end = self.pos + n
        if end > len(self.buf):
            raise SaveError(f"unexpected end at {self.pos}")
        out = self.buf[self.pos:end]
        self.pos = end
        return out

    def u16(self) -> int:
        return struct.unpack("<H", self.take(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.take(8))[0]

    def u8(self) -> int:
        return self.take(1)[0]

    def string(self) -> str:
        return self.take(self.u32()).decode("utf-8", "replace")


def parse(data: bytes) -> tuple[dict, dict]:
    """Return (header, game_state). Raises SaveError on malformed input."""
    if data[:4] != MAGIC:
        raise SaveError("not an SGB1 save")
    checksum = struct.unpack("<I", data[4:8])[0]
    if zlib.adler32(data[8:]) & 0xFFFFFFFF != checksum:
        raise SaveError("checksum mismatch")

    c = _Cursor(data, 8)
    header = {
        "version": c.u16(),
        "version_unk": c.u16(),
        "timestamp": c.u64(),
        "location": c.string(),
        "runs": c.u32(),
        "accumulated_meta_points": c.u32(),
        "active_shrine_points": c.u32(),
        "grasp": c.u32(),
        "easy_mode": bool(c.u8()),
        "hard_mode": bool(c.u8()),
    }
    if header["version"] >= 18:
        header["unknown_v18"] = c.u32()
    header["lua_keys"] = [c.string() for _ in range(c.u32())]
    header["current_map_name"] = c.string()
    header["start_next_map"] = c.string()

    blob = c.take(c.u32())
    if c.pos != len(data):
        raise SaveError("trailing bytes after lua blob")

    raw = lz4.block.decompress(blob, uncompressed_size=DECOMPRESSED_LEN)
    values = luabins.loads(raw)
    if len(values) != 1 or not isinstance(values[0], dict):
        raise SaveError("lua state is not a single table")
    return header, values[0]


def parse_file(path: str | pathlib.Path) -> tuple[dict, dict]:
    return parse(pathlib.Path(path).read_bytes())


def main() -> None:
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Dump a Hades II save to JSON")
    ap.add_argument("save")
    ap.add_argument("--header-only", action="store_true")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    header, state = parse_file(args.save)
    if args.header_only:
        print(json.dumps(header, indent=2))
        return
    payload = {"header": header, "state": state}
    text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    if args.output:
        pathlib.Path(args.output).write_text(text, encoding="utf-8")
        print(f"wrote {args.output} ({len(text)} bytes)")
    else:
        print(text)


if __name__ == "__main__":
    main()
