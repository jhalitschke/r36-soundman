#!/usr/bin/env python3
"""Smoke-Test für einen gebauten libretro-Core (x86-Compile-Check, kein Gerät nötig).

    python3 tests/core_smoke.py cores/adl/adl_libretro.so

Prüft: .so lädt, libretro-API-Version, alle Pflichtsymbole exportiert,
AV-Info entspricht den Konventionen (48 kHz, 60 fps, 320x240) und die
Angaben in der .info-Datei passen zu denen des Cores.
"""
import ctypes
import sys
from pathlib import Path

PFLICHT = [
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


def info_datei(so):
    """<name>_libretro.info neben dem Core als dict."""
    pfad = so.with_suffix(".info")
    werte = {}
    for zeile in pfad.read_text().splitlines():
        if "=" in zeile:
            k, _, v = zeile.partition("=")
            werte[k.strip()] = v.strip().strip('"')
    return pfad, werte


def main(argv):
    so = Path(argv[1] if len(argv) > 1 else "cores/adl/adl_libretro.so").resolve()
    fehler = []
    lib = ctypes.CDLL(str(so))

    for sym in PFLICHT:
        if not hasattr(lib, sym):
            fehler.append("Symbol fehlt: %s" % sym)

    lib.retro_api_version.restype = ctypes.c_uint
    version = lib.retro_api_version()
    if version != 1:
        fehler.append("retro_api_version = %d, erwartet 1" % version)

    si = SystemInfo()
    lib.retro_get_system_info(ctypes.byref(si))
    av = AvInfo()
    lib.retro_get_system_av_info(ctypes.byref(av))

    # Konventionen aus CLAUDE.md: 48 kHz, 60 fps, 320x240.
    for name, ist, soll in (("sample_rate", av.timing.sample_rate, 48000.0),
                            ("fps", av.timing.fps, 60.0),
                            ("base_width", av.geometry.base_width, 320),
                            ("base_height", av.geometry.base_height, 240)):
        if ist != soll:
            fehler.append("%s = %s, erwartet %s" % (name, ist, soll))

    pfad, meta = info_datei(so)
    name = si.library_name.decode()
    exts = si.valid_extensions.decode()
    if meta.get("corename") != name:
        fehler.append("%s: corename=%r, Core meldet %r" % (pfad.name, meta.get("corename"), name))
    if meta.get("supported_extensions") != exts:
        fehler.append("%s: supported_extensions=%r, Core meldet %r"
                      % (pfad.name, meta.get("supported_extensions"), exts))
    if meta.get("display_version") != si.library_version.decode():
        fehler.append("%s: display_version=%r, Core meldet %r"
                      % (pfad.name, meta.get("display_version"), si.library_version.decode()))

    print("%s: %s %s, ext=%s, %dx%d @ %g fps, %g Hz, API %d"
          % (so.name, name, si.library_version.decode(), exts, av.geometry.base_width,
             av.geometry.base_height, av.timing.fps, av.timing.sample_rate, version))
    for f in fehler:
        print("FEHLER: " + f, file=sys.stderr)
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
