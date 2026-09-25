#!/usr/bin/env bash
# Läuft im arm64-Container (scripts/build.sh picoloop). Ergebnis: ports/picoloop/picoloop
set -euo pipefail
cd "$(dirname "$0")"
[ -d src ] || git clone --depth 1 https://github.com/yoyz/audio src
cd src/picoloop
# Engines, die den RK3326 überfordern, in Master.h abschalten (Twytch/Helm, Open303, Cursynth).
# Die Makefile-Namen im Repo prüfen und unten den SDL2-Linux-Build eintragen:
ls Makefile* 2>/dev/null || true
MK=${MK:-$(ls Makefile*linux*sdl2* 2>/dev/null | head -1)}
[ -n "$MK" ] || { echo "SDL2-Linux-Makefile nicht gefunden – MK=<name> setzen"; exit 1; }
make -f "$MK" -j"$(nproc)"
cp -v picoloop ../../picoloop
mkdir -p ../../lib && cp -v /usr/lib/aarch64-linux-gnu/libSDL2-2.0.so.0 ../../lib/ 2>/dev/null || true
cp -rn patch ../../ 2>/dev/null || true
