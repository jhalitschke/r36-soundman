#!/bin/bash
# %ROM% = the empty marker song.lgpt in a project folder; LGPT opens that folder.
#
# LittleGPTracker comes from PortMaster (littlegptracker.zip). Its own launcher,
# /roms/ports/LittleGPTracker.sh, takes no arguments at all - it cds into the
# port and runs ./lgpt bare - so this cannot simply call it and hand it a
# project. What it does set up has to be repeated here instead: the library and
# XDG paths, the screen multiplier its config wants, and gptokeyb with the
# port's own key map.
controlfolder="/opt/system/Tools/PortMaster"
[ -f "$controlfolder/control.txt" ] || { echo "PortMaster control.txt not found in $controlfolder" >&2; exit 1; }
source "$controlfolder/control.txt"
# shellcheck disable=SC1090  # the name comes from control.txt, like upstream's own launcher
[ -f "${controlfolder}/mod_${CFW_NAME}.txt" ] && source "${controlfolder}/mod_${CFW_NAME}.txt"
get_controls
[ -n "${GPTOKEYB:-}" ] || { echo "control.txt did not set GPTOKEYB" >&2; exit 1; }

LGPT_DIR=${LGPT_DIR:-/roms/ports/littlegptracker}
LGPT_BIN=${LGPT_BIN:-$LGPT_DIR/lgpt}
[ -x "$LGPT_BIN" ] || { echo "no LGPT at $LGPT_BIN - install littlegptracker.zip with PortMaster" >&2; exit 1; }
[ -n "${1:-}" ] || { echo "usage: lgpt.sh <project>/song.lgpt" >&2; exit 1; }

PROJECT=$(dirname "$1")
export DEVICE_ARCH="${DEVICE_ARCH:-aarch64}"
export LD_LIBRARY_PATH="/usr/lib/:/usr/lib/aarch64-linux-gnu/:$LD_LIBRARY_PATH"
# LGPT keeps its config next to itself, not next to the song
export XDG_CONFIG_HOME="$LGPT_DIR" XDG_DATA_HOME="$LGPT_DIR"

# The port's launcher works this out from the panel and writes it into its own
# config; the same has to happen here or LGPT comes up at 1x on a 480p screen.
if [ -n "${DISPLAY_WIDTH:-}" ] && [ -n "${DISPLAY_HEIGHT:-}" ]; then
  MULT_W=$((DISPLAY_WIDTH / 320)); MULT_H=$((DISPLAY_HEIGHT / 240))
  MULT=$((MULT_W < MULT_H ? MULT_W : MULT_H)); [ "$MULT" -le 0 ] && MULT=1
  sed -i "s/SCREENMULT value='[0-9]'/SCREENMULT value='$MULT'/" "$LGPT_DIR/config.xml" 2>/dev/null
fi

cd "$LGPT_DIR" || exit 1
$GPTOKEYB "lgpt" -c "$LGPT_DIR/lgpt.gptk" &
./lgpt "$PROJECT" > /roms/ports/lgpt/log.txt 2>&1
# shellcheck disable=SC2046  # pidof may return several PIDs, the splitting is intended
$ESUDO kill -9 $(pidof gptokeyb) 2>/dev/null
