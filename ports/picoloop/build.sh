#!/usr/bin/env bash
# Runs inside the arm64 container (scripts/build.sh picoloop). Result: ports/picoloop/picoloop
#
# Makefile choice: the picoloop repo has no "linux sdl2" makefile - the one that
# fits the RK3326 is the Raspberry Pi 1 target. It builds SDL2, uses fixed-point
# maths (-DFIXED) and compiles only the four light engines (Picosynth, Picodrum,
# OPL2, PBSynth), so Twytch/Open303/Cursynth do not need switching off by hand.
set -euo pipefail
cd "$(dirname "$0")"
[ -d src ] || git clone --depth 1 https://github.com/yoyz/audio src
cd src/picoloop
MK=${MK:-Makefile.PatternPlayer_raspi1_RtAudio_sdl20}
[ -f "$MK" ] || { echo "makefile $MK not found - candidates:"; ls Makefile*sdl20*; exit 1; }

# ArkOS has no PulseAudio: build RtAudio against ALSA and do not link libpulse.
sed 's/-D__LINUX_PULSE__/-D__LINUX_ALSA__/g; s/-lpulse -lpulse-simple//g' "$MK" > Makefile.r36s
make -f Makefile.r36s -j"$(nproc)"

# The makefile builds with -ggdb; the debug info is a third of the binary.
strip PatternPlayer_raspi1_sdl20
cp -v PatternPlayer_raspi1_sdl20 ../../picoloop
cp -v font.ttf font.bmp ../../          # the app looks for both next to itself

# No libraries are bundled on purpose. The binary needs libSDL2, libSDL2_ttf and
# libasound, and Ubuntu's libSDL2 drags in pulse, wayland, X11 and systemd - on
# ArkOS that chain does not exist, and picoloop.sh puts ports/picoloop/lib/ first
# in LD_LIBRARY_PATH, so a bundled Ubuntu SDL2 would win over the device's
# working one and fail to load. Compare the list below against the device
# (device/<host>/inventory.txt) and bundle only what is genuinely missing.
echo "== shared libraries this binary needs on the device"
readelf -d ../../picoloop | grep -oE '\[lib[^]]+\]' | tr -d '[]'
