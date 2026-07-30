#!/usr/bin/env python3
"""Read and extract the Slay the Spire 2 Godot .pck archive.

The game ships as Godot 4.5 with an unencrypted PCK (pack format 3), so the
localization JSON, patch-note Markdown and texture data can be pulled straight
out of the install without any third-party tooling.

Examples:
    python3 scripts/pck_extract.py --list
    python3 scripts/pck_extract.py --extract 'localization/**' --out artifacts/pck
    python3 scripts/pck_extract.py --extract 'images/**' --decode-textures --resolve-imports
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator

DEFAULT_PCK = Path(
    "~/Library/Application Support/Steam/steamapps/common/Slay the Spire 2"
    "/SlayTheSpire2.app/Contents/Resources/Slay the Spire 2.pck"
).expanduser()

PACK_MAGIC = b"GDPC"
PACK_DIR_ENCRYPTED = 1
PACK_REL_FILEBASE = 2

# Godot's CompressedTexture2D payload encodings.
DATA_FORMAT_IMAGE = 0
DATA_FORMAT_PNG = 1
DATA_FORMAT_WEBP = 2
DATA_FORMAT_BASIS_UNIVERSAL = 3

# Image::Format values that are GPU block-compressed, mapped to a DDS FourCC.
BLOCK_FOURCC = {17: b"DXT1", 18: b"DXT3", 19: b"DXT5"}
BLOCK_DX10 = {22: 98}  # BPTC_RGBA -> DXGI_FORMAT_BC7_UNORM
BLOCK_BYTES = {17: 8, 18: 16, 19: 16, 22: 16}  # bytes per 4x4 block


@dataclass(frozen=True)
class Entry:
    path: str
    offset: int
    size: int
    md5: bytes
    flags: int


class PackError(RuntimeError):
    pass


def _read_header(fh: BinaryIO) -> tuple[int, int, tuple[int, int, int]]:
    """Return (file_base, directory_offset_hint, engine_version)."""
    head = fh.read(0x28)
    if head[:4] != PACK_MAGIC:
        raise PackError(f"not a Godot pack (magic {head[:4]!r})")
    pack_version, major, minor, patch, flags = struct.unpack("<IIIII", head[4:24])
    if pack_version not in (2, 3):
        raise PackError(f"unsupported pack format version {pack_version}")
    if flags & PACK_DIR_ENCRYPTED:
        raise PackError("pack directory is encrypted; a script key is required")
    file_base, dir_hint = struct.unpack("<QQ", head[24:40])
    if not flags & PACK_REL_FILEBASE:
        file_base = 0
    return file_base, dir_hint, (major, minor, patch)


def _try_walk(fh: BinaryIO, start: int, eof: int) -> int | None:
    """Return the entry count if a directory at `start` ends exactly at EOF."""
    fh.seek(start)
    raw = fh.read(4)
    if len(raw) < 4:
        return None
    count = struct.unpack("<I", raw)[0]
    if not 0 < count < 2_000_000:
        return None
    pos = start + 4
    for _ in range(count):
        fh.seek(pos)
        raw = fh.read(4)
        if len(raw) < 4:
            return None
        path_len = struct.unpack("<I", raw)[0]
        # Paths are NUL-padded to a 4-byte boundary.
        if path_len == 0 or path_len > 1024 or path_len % 4:
            return None
        pos += 4 + path_len + 36  # + offset,size (16) + md5 (16) + flags (4)
        if pos > eof:
            return None
    return count if pos == eof else None


def _find_directory(fh: BinaryIO, hint: int, eof: int) -> tuple[int, int]:
    """Locate the file index.

    The v3 header's directory field trails the real offset by the tail padding,
    so treat it as a lower bound and scan forward on the 8-byte alignment Godot
    writes the index at.
    """
    for start in (hint, hint + 8):
        count = _try_walk(fh, start, eof)
        if count is not None:
            return start, count
    floor = max(0, min(hint, eof - 64 * 1024 * 1024))
    for start in range(floor - floor % 8, eof, 8):
        count = _try_walk(fh, start, eof)
        if count is not None:
            return start, count
    raise PackError("could not locate the pack file index")


class Pack:
    """Random-access reader over a Godot .pck file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fh = path.open("rb")
        eof = path.stat().st_size
        file_base, hint, self.engine_version = _read_header(self._fh)
        dir_start, count = _find_directory(self._fh, hint, eof)
        self._fh.seek(dir_start + 4)
        self.entries: dict[str, Entry] = {}
        for _ in range(count):
            path_len = struct.unpack("<I", self._fh.read(4))[0]
            name = self._fh.read(path_len).rstrip(b"\0").decode("utf-8")
            offset, size = struct.unpack("<QQ", self._fh.read(16))
            md5 = self._fh.read(16)
            flags = struct.unpack("<I", self._fh.read(4))[0]
            self.entries[name] = Entry(name, offset + file_base, size, md5, flags)

    def __enter__(self) -> Pack:
        return self

    def __exit__(self, *exc: object) -> None:
        self._fh.close()

    def read(self, name: str) -> bytes:
        entry = self.entries[name]
        self._fh.seek(entry.offset)
        return self._fh.read(entry.size)

    def verify(self, name: str) -> bool:
        return hashlib.md5(self.read(name)).digest() == self.entries[name].md5

    def match(self, patterns: list[str]) -> Iterator[Entry]:
        for entry in self.entries.values():
            if any(fnmatch.fnmatch(entry.path, pat) for pat in patterns):
                yield entry

    def import_map(self) -> dict[str, str]:
        """Map each source asset path to the .ctex/.spskel it was baked into.

        VRAM-compressed textures have no plain `path=`; they list one baked file
        per GPU format (`path.bptc=`, `path.s3tc=`, ...), so pick the best
        available variant.
        """
        preference = ("", "bptc", "s3tc", "etc2", "astc")
        mapping: dict[str, str] = {}
        for name in self.entries:
            if not name.endswith(".import"):
                continue
            variants: dict[str, str] = {}
            for line in self.read(name).decode("utf-8", "replace").splitlines():
                match = re.match(r'path(?:\.(\w+))?="res://(.+)"$', line)
                if match:
                    variants[match.group(1) or ""] = match.group(2)
            for key in preference:
                if key in variants:
                    mapping[name[: -len(".import")]] = variants[key]
                    break
        return mapping


def _dds_header(fourcc: bytes | None, dxgi: int | None, width: int, height: int, linear_size: int) -> bytes:
    """Wrap block-compressed mip 0 so Pillow/Preview-class tools can read it."""
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000  # CAPS|HEIGHT|WIDTH|PIXELFORMAT|LINEARSIZE
    pixel_format = struct.pack(
        "<II4sIIIII", 32, 0x4, fourcc or b"DX10", 0, 0, 0, 0, 0  # DDPF_FOURCC
    )
    header = (
        b"DDS "
        + struct.pack("<IIIIIII", 124, flags, height, width, linear_size, 0, 0)
        + b"\0" * 44  # dwReserved1
        + pixel_format
        + struct.pack("<IIIII", 0x1000, 0, 0, 0, 0)  # DDSCAPS_TEXTURE, caps2-4, reserved2
    )
    if fourcc:
        return header
    # DX10 extension: dxgiFormat, D3D10_RESOURCE_DIMENSION_TEXTURE2D, misc, arraySize, misc2
    return header + struct.pack("<IIIII", dxgi or 0, 3, 0, 1, 0)


def decode_texture(data: bytes) -> tuple[str, bytes] | None:
    """Return (suffix, bytes) for a .ctex payload, or None if unsupported."""
    if data[:4] != b"GST2":
        return None
    width, height = struct.unpack("<II", data[8:16])
    data_format, = struct.unpack("<I", data[36:40])
    if data_format in (DATA_FORMAT_PNG, DATA_FORMAT_WEBP):
        size, = struct.unpack("<I", data[52:56])
        blob = data[56 : 56 + size]
        return (".png" if data_format == DATA_FORMAT_PNG else ".webp", blob)
    if data_format == DATA_FORMAT_IMAGE:
        image_format, = struct.unpack("<I", data[48:52])
        payload = data[52:]
        if image_format in BLOCK_BYTES:
            # DDS describes mip 0 only; any trailing mip levels are simply ignored.
            block = BLOCK_BYTES[image_format]
            linear = max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * block
            if image_format in BLOCK_FOURCC:
                head = _dds_header(BLOCK_FOURCC[image_format], None, width, height, linear)
            else:
                head = _dds_header(None, BLOCK_DX10[image_format], width, height, linear)
            return (".dds", head + payload)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pck", type=Path, default=DEFAULT_PCK, help="path to the .pck (defaults to the Steam install)")
    parser.add_argument("--list", action="store_true", help="print the file index instead of extracting")
    parser.add_argument("--extract", metavar="GLOB", action="append", default=[], help="glob of paths to extract (repeatable)")
    parser.add_argument("--out", type=Path, default=Path("artifacts/pck"), help="output directory")
    parser.add_argument("--decode-textures", action="store_true", help="unwrap .ctex into .webp/.png/.dds")
    parser.add_argument("--resolve-imports", action="store_true", help="write textures under their source asset path")
    parser.add_argument("--verify", action="store_true", help="check every extracted file against its stored MD5")
    args = parser.parse_args(argv)

    if not args.pck.exists():
        parser.error(f"pck not found: {args.pck}")

    with Pack(args.pck) as pack:
        print(f"Godot {'.'.join(map(str, pack.engine_version))} pack, {len(pack.entries)} files", file=sys.stderr)

        if args.list or not args.extract:
            for entry in sorted(pack.entries.values(), key=lambda e: e.path):
                print(f"{entry.size:>10}  {entry.path}")
            return 0

        # A texture's real name lives in its .import sidecar, not the baked path.
        ctex_to_source: dict[str, str] = {}
        if args.resolve_imports:
            ctex_to_source = {v: k for k, v in pack.import_map().items()}

        written = failed = 0
        for entry in pack.match(args.extract):
            data = pack.read(entry.path)
            if args.verify and hashlib.md5(data).digest() != entry.md5:
                print(f"MD5 mismatch: {entry.path}", file=sys.stderr)
                failed += 1
                continue

            rel = ctex_to_source.get(entry.path, entry.path)
            if args.decode_textures and entry.path.endswith(".ctex"):
                decoded = decode_texture(data)
                if decoded is None:
                    print(f"unsupported texture payload: {entry.path}", file=sys.stderr)
                    failed += 1
                    continue
                suffix, data = decoded
                rel = str(Path(rel).with_suffix("")) if rel.endswith(".ctex") else rel
                rel = str(Path(rel).with_suffix(suffix))

            dest = args.out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            written += 1

        print(f"wrote {written} files to {args.out}" + (f" ({failed} failed)" if failed else ""), file=sys.stderr)
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
