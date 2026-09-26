#!/usr/bin/env python3
"""Refuse a binary that needs newer symbol versions than the device can serve.

    scripts/glibc-check.py cores/adl/adl_libretro.so
    scripts/glibc-check.py --max GLIBC_2.30 --max GLIBCXX_3.4.28 <file>...

The container the cores are cross-built in does not have to match the device's
Ubuntu release - only the symbol versions the linker ended up binding have to be
ones the device provides. Most are GLIBC_2.17 on aarch64, the base version,
whatever the build image is; a handful of functions carry newer defaults and
those are the ones worth catching. The C++ runtime matters just as much, since
the cores link libstdc++ for their upstream library.

A version family with no limit given is ignored - GCC_3.0 and the like say
nothing useful. The defaults describe r36a, measured rather than assumed:
see device/<host>/inventory.txt and the libstdc++ on the device itself.

Reads the ELF rather than shelling out to readelf, so it works on a host without
binutils and against a foreign architecture. What a binary needs is listed in
.gnu.version_r, which is exactly the question being asked.
"""
import struct
import sys
from pathlib import Path

SHT_GNU_VERNEED = 0x6FFFFFFE


def _sections(blob):
    """Every section header as (name, type, offset, size, link), plus endianness."""
    if blob[:4] != b"\x7fELF":
        raise ValueError("not an ELF file")
    is64 = blob[4] == 2
    e = "<" if blob[5] == 1 else ">"

    if is64:
        shoff, = struct.unpack_from(e + "Q", blob, 0x28)
        shentsize, shnum, shstrndx = struct.unpack_from(e + "HHH", blob, 0x3A)
        offs = (0x18, 0x20, 0x28, "Q")
    else:
        shoff, = struct.unpack_from(e + "I", blob, 0x20)
        shentsize, shnum, shstrndx = struct.unpack_from(e + "HHH", blob, 0x2E)
        offs = (0x10, 0x14, 0x18, "I")
    off_o, size_o, link_o, word = offs

    out = []
    for i in range(shnum):
        b = shoff + i * shentsize
        name, typ = struct.unpack_from(e + "II", blob, b)
        off, = struct.unpack_from(e + word, blob, b + off_o)
        size, = struct.unpack_from(e + word, blob, b + size_o)
        link, = struct.unpack_from(e + "I", blob, b + link_o)
        out.append([name, typ, off, size, link])

    shstr = out[shstrndx][2]
    for sec in out:
        at = shstr + sec[0]
        sec[0] = blob[at:blob.index(b"\0", at)].decode()
    return out, e


def _cstr(blob, at):
    return blob[at:blob.index(b"\0", at)].decode()


def needed_versions(path):
    """Every versioned symbol requirement, as {library: {version, ...}}.

    .gnu.version_r is a chain of Verneed records - one per library - each with a
    chain of Vernaux records naming the versions wanted from it. Both chains use
    byte offsets to the next entry rather than a count of bytes, so they have to
    be walked rather than sliced.
    """
    blob = Path(path).read_bytes()
    secs, e = _sections(blob)
    out = {}
    for name, typ, off, size, link in secs:
        if typ != SHT_GNU_VERNEED:
            continue
        strtab = secs[link][2]
        pos = off
        while True:
            # Elf_Verneed: version, cnt, file, aux, next
            _, cnt, file_off, aux_off, next_off = struct.unpack_from(e + "HHIII", blob, pos)
            lib = _cstr(blob, strtab + file_off)
            aux = pos + aux_off
            for _ in range(cnt):
                # Elf_Vernaux: hash, flags, other, name, next
                _, _, _, name_off, aux_next = struct.unpack_from(e + "IHHII", blob, aux)
                out.setdefault(lib, set()).add(_cstr(blob, strtab + name_off))
                if not aux_next:
                    break
                aux += aux_next
            if not next_off:
                break
            pos += next_off
    return out


# Measured on r36a: Ubuntu 19.10 with libc-2.30 and libstdc++.so.6.0.28.
DEFAULT_LIMITS = {"GLIBC": "2.30", "GLIBCXX": "3.4.28", "CXXABI": "1.3.12"}


def as_tuple(version):
    return tuple(int(p) for p in version.split("."))


def split_version(symbol):
    """"GLIBCXX_3.4.21" -> ("GLIBCXX", "3.4.21"), or None if it is not one."""
    family, _, version = symbol.rpartition("_")
    if not family or not version or not version[0].isdigit():
        return None
    try:
        as_tuple(version)
    except ValueError:
        return None
    return family, version


def main(argv):
    limits = {}
    files = []
    i = 0
    while i < len(argv):
        if argv[i] == "--max":
            i += 1
            if i >= len(argv):
                print("--max needs a value, e.g. GLIBC_2.30")
                return 2
            # a bare number keeps the old spelling working
            arg = argv[i] if "_" in argv[i] else "GLIBC_" + argv[i]
            parsed = split_version(arg)
            if not parsed:
                print(f"--max: cannot read {argv[i]!r} as a version")
                return 2
            limits[parsed[0]] = parsed[1]
        elif argv[i] in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            files.append(argv[i])
        i += 1
    if not files:
        print(__doc__)
        return 2
    limits = {**DEFAULT_LIMITS, **limits}

    rc = 0
    for f in files:
        try:
            needs = needed_versions(f)
        except (ValueError, IndexError, struct.error) as exc:
            print(f"{f}: cannot read ({exc})")
            rc = 1
            continue
        print(f"{Path(f).name}:")
        if not needs:
            print("  no versioned symbol requirements at all")
        too_new = []
        for lib, versions in sorted(needs.items()):
            print(f"  {lib:<24} {' '.join(sorted(versions))}")
            for v in versions:
                parsed = split_version(v)
                if not parsed:
                    continue
                family, version = parsed
                if family in limits and as_tuple(version) > as_tuple(limits[family]):
                    too_new.append(f"{lib} needs {v}, device has {family}_{limits[family]}")
        for line in sorted(too_new):
            print(f"  -> {line}")
        if too_new:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
