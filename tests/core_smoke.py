#!/usr/bin/env python3
"""Smoke test for a built libretro core (x86 compile check, no device needed).

    python3 tests/core_smoke.py cores/adl/adl_libretro.so

Checks: the .so loads, the libretro API version, that every mandatory symbol is
exported, that the AV info matches the conventions (48 kHz, 60 fps, 320x240) and
that the .info file agrees with what the core reports.
"""
import ctypes
import sys
from pathlib import Path

MANDATORY = [
    "retro_api_version", "retro_init", "retro_deinit", "retro_get_system_info",
    "retro_get_system_av_info", "retro_set_environment", "retro_set_video_refresh",
    "retro_set_audio_sample", "retro_set_audio_sample_batch", "retro_set_input_poll",
    "retro_set_input_state", "retro_set_controller_port_device", "retro_reset",
    "retro_run", "retro_serialize_size", "retro_serialize", "retro_unserialize",
    "retro_cheat_reset", "retro_cheat_set", "retro_load_game", "retro_unload_game",
    "retro_get_region", "retro_get_memory_data", "retro_get_memory_size",
]


class SystemInfo(ctypes.Structure):
    _fields_ = [("library_name", ctypes.c_char_p), ("library_version", ctypes.c_char_p),
                ("valid_extensions", ctypes.c_char_p), ("need_fullpath", ctypes.c_bool),
                ("block_extract", ctypes.c_bool)]


class Geometry(ctypes.Structure):
    _fields_ = [("base_width", ctypes.c_uint), ("base_height", ctypes.c_uint),
                ("max_width", ctypes.c_uint), ("max_height", ctypes.c_uint),
                ("aspect_ratio", ctypes.c_float)]


class Timing(ctypes.Structure):
    _fields_ = [("fps", ctypes.c_double), ("sample_rate", ctypes.c_double)]


class AvInfo(ctypes.Structure):
    _fields_ = [("geometry", Geometry), ("timing", Timing)]


def info_file(so):
    """<name>_libretro.info next to the core, as a dict."""
    path = so.with_suffix(".info")
    values = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            values[k.strip()] = v.strip().strip('"')
    return path, values


def main(argv):
    so = Path(argv[1] if len(argv) > 1 else "cores/adl/adl_libretro.so").resolve()
    problems = []
    # dlopen reports a foreign architecture as "No such file or directory",
    # which sends you looking for a missing file that is right there.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import elfinfo
    if not elfinfo.is_host_arch(so):
        print(f"{so.name} is not this machine's architecture - built for the device?")
        return 1
    lib = ctypes.CDLL(str(so))

    for sym in MANDATORY:
        if not hasattr(lib, sym):
            problems.append("missing symbol: %s" % sym)

    lib.retro_api_version.restype = ctypes.c_uint
    version = lib.retro_api_version()
    if version != 1:
        problems.append("retro_api_version = %d, expected 1" % version)

    si = SystemInfo()
    lib.retro_get_system_info(ctypes.byref(si))
    av = AvInfo()
    lib.retro_get_system_av_info(ctypes.byref(av))

    # Conventions from CLAUDE.md: 48 kHz, 60 fps, 320x240.
    for name, actual, expected in (("sample_rate", av.timing.sample_rate, 48000.0),
                                   ("fps", av.timing.fps, 60.0),
                                   ("base_width", av.geometry.base_width, 320),
                                   ("base_height", av.geometry.base_height, 240)):
        if actual != expected:
            problems.append("%s = %s, expected %s" % (name, actual, expected))

    path, meta = info_file(so)
    name = si.library_name.decode()
    exts = si.valid_extensions.decode()
    if meta.get("corename") != name:
        problems.append("%s: corename=%r, core reports %r" % (path.name, meta.get("corename"), name))
    if meta.get("supported_extensions") != exts:
        problems.append("%s: supported_extensions=%r, core reports %r"
                        % (path.name, meta.get("supported_extensions"), exts))
    if meta.get("display_version") != si.library_version.decode():
        problems.append("%s: display_version=%r, core reports %r"
                        % (path.name, meta.get("display_version"), si.library_version.decode()))

    print("%s: %s %s, ext=%s, %dx%d @ %g fps, %g Hz, API %d"
          % (so.name, name, si.library_version.decode(), exts, av.geometry.base_width,
             av.geometry.base_height, av.timing.fps, av.timing.sample_rate, version))
    for problem in problems:
        print("FAIL: " + problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
