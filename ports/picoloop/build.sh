#!/usr/bin/env bash
# Runs inside the arm64 container (scripts/build.sh picoloop). Result: ports/picoloop/picoloop
set -euo pipefail
cd "$(dirname "$0")"
[ -d src ] || git clone --depth 1 https://github.com/yoyz/audio src
cd src/picoloop
# Disable the engines that overwhelm the RK3326 in Master.h (Twytch/Helm, Open303, Cursynth).
# Check the makefile names in the repo and put the SDL2 Linux build in below:
ls Makefile* 2>/dev/null || true
MK=${MK:-$(ls Makefile*linux*sdl2* 2>/dev/null | head -1)}
[ -n "$MK" ] || { echo "no SDL2 Linux makefile found - set MK=<name>"; exit 1; }
make -f "$MK" -j"$(nproc)"
cp -v picoloop ../../picoloop
mkdir -p ../../lib && cp -v /usr/lib/aarch64-linux-gnu/libSDL2-2.0.so.0 ../../lib/ 2>/dev/null || true
cp -rn patch ../../ 2>/dev/null || true
