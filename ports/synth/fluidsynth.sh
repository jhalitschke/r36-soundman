#!/bin/bash
# FluidSynth as an ES "system": %ROM% = the soundfont. Select+Start quits (gptokeyb kills fluidsynth).
# Requires fluidsynth + libfluidsynth installed as arm64 .deb (see README phase 4.1)
controlfolder="/opt/system/Tools/PortMaster"
source "$controlfolder/control.txt"
get_controls
PERIOD=${PERIOD:-256}; COUNT=${COUNT:-2}   # the latency knobs
cd /roms/synth || exit 1
$GPTOKEYB "fluidsynth" &
fluidsynth -i -a alsa -o audio.alsa.device=hw:0 -m alsa_seq -o midi.autoconnect=1 \
  -r 48000 -z "$PERIOD" -c "$COUNT" "$1" > /roms/ports/synth/log.txt 2>&1
# shellcheck disable=SC2046  # pidof may return several PIDs, the splitting is intended
$ESUDO kill -9 $(pidof gptokeyb) 2>/dev/null
