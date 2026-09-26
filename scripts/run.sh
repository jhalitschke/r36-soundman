#!/usr/bin/env bash
# Stop ES, run a command on the device in the foreground, start ES again.
# scripts/run.sh r36a 'fluidsynth -i -a alsa -m alsa_seq /roms/synth/x.sf2'
set -uo pipefail
HOST=$1; shift
ssh -t "$HOST" "sudo systemctl stop emulationstation; $*; sudo systemctl start emulationstation"
