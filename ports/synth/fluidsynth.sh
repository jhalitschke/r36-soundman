#!/bin/bash
# FluidSynth als ES-"System": %ROM% = Soundfont. Select+Start beendet (gptokeyb killt fluidsynth).
# Voraussetzung: fluidsynth + libfluidsynth als arm64-.deb installiert (siehe README Phase 4.1)
controlfolder="/opt/system/Tools/PortMaster"
source "$controlfolder/control.txt"
get_controls
PERIOD=${PERIOD:-256}; COUNT=${COUNT:-2}   # Latenz-Schrauben
cd /roms/synth || exit 1
$GPTOKEYB "fluidsynth" &
fluidsynth -i -a alsa -o audio.alsa.device=hw:0 -m alsa_seq -o midi.autoconnect=1 \
  -r 48000 -z "$PERIOD" -c "$COUNT" "$1" > /roms/ports/synth/log.txt 2>&1
# shellcheck disable=SC2046  # pidof kann mehrere PIDs liefern, Splitting ist gewollt
$ESUDO kill -9 $(pidof gptokeyb) 2>/dev/null
