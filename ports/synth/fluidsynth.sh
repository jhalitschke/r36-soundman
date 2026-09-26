#!/bin/bash
# FluidSynth as an ES "system": %ROM% = the soundfont. Select+Start quits (gptokeyb kills fluidsynth).
# Requires fluidsynth + libfluidsynth installed as arm64 .deb (see README phase 4.1)
controlfolder="/opt/system/Tools/PortMaster"
[ -f "$controlfolder/control.txt" ] || { echo "PortMaster control.txt not found in $controlfolder" >&2; exit 1; }
source "$controlfolder/control.txt"
get_controls
[ -n "${GPTOKEYB:-}" ] || { echo "control.txt did not set GPTOKEYB" >&2; exit 1; }
PERIOD=${PERIOD:-256}; COUNT=${COUNT:-2}   # the latency knobs
cd /roms/synth || exit 1
$GPTOKEYB "fluidsynth" &
# nice -19 like every one of ArkOS's own 123 commands: on this device a normal
# user may lower its niceness but may not have realtime priority at all
# (RLIMIT_RTPRIO is 0), which is why fluidsynth warns "Failed to set thread to
# high priority" and why -19 is the most that can be done for it here.
nice -n -19 fluidsynth -i -a alsa -o audio.alsa.device=hw:0 -m alsa_seq -o midi.autoconnect=1 \
  -r 48000 -z "$PERIOD" -c "$COUNT" "$1" > /roms/ports/synth/log.txt 2>&1
# shellcheck disable=SC2046  # pidof may return several PIDs, the splitting is intended
$ESUDO kill -9 $(pidof gptokeyb) 2>/dev/null
