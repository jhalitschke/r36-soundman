#!/usr/bin/env python3
"""Whether an ELF can be loaded by the host that is running the tests.

scripts/build.sh leaves an aarch64 .so in the same place a host-side
"make -C cores/adl" would leave an x86 one. dlopen then fails with
"cannot open shared object file: No such file or directory", which reads like a
missing file and is really a foreign architecture - so the tests check first
and skip instead of erroring.
"""
import platform
import struct
from pathlib import Path

# e_machine values, against what platform.machine() calls the same thing
MACHINES = {
    0x03: {"i386", "i686"},
    0x28: {"arm", "armv7l", "armv6l"},
    0x3E: {"x86_64", "amd64"},
    0xB7: {"aarch64", "arm64"},
    0xF3: {"riscv64"},
}


def machine(path):
    """The ELF's e_machine, or None if it is not an ELF at all."""
    blob = Path(path).read_bytes()[:20]
    if blob[:4] != b"\x7fELF":
        return None
    endian = "<" if blob[5] == 1 else ">"
    return struct.unpack_from(endian + "H", blob, 0x12)[0]


def is_host_arch(path):
    try:
        m = machine(path)
    except OSError:
        return False
    if m is None:
        return False
    return platform.machine().lower() in MACHINES.get(m, set())
