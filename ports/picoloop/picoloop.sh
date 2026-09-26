#!/bin/bash
controlfolder="/opt/system/Tools/PortMaster"
[ -f "$controlfolder/control.txt" ] || { echo "PortMaster control.txt not found in $controlfolder" >&2; exit 1; }
source "$controlfolder/control.txt"
get_controls
[ -n "${GPTOKEYB:-}" ] || { echo "control.txt did not set GPTOKEYB" >&2; exit 1; }
cd /roms/ports/picoloop || exit 1
export LD_LIBRARY_PATH="$PWD/lib:$LD_LIBRARY_PATH"
export SDL_VIDEODRIVER=KMSDRM SDL_AUDIODRIVER=alsa
$GPTOKEYB "picoloop" -c ./keys.gptk &
./picoloop > log.txt 2>&1
# shellcheck disable=SC2046  # pidof may return several PIDs, the splitting is intended
$ESUDO kill -9 $(pidof gptokeyb) 2>/dev/null
