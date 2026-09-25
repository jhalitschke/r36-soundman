#!/usr/bin/env bash
# ES stoppen, Kommando auf dem Gerät im Vordergrund laufen lassen, ES wieder starten.
# scripts/run.sh r36a 'fluidsynth -i -a alsa -m alsa_seq /roms/synth/x.sf2'
set -uo pipefail
HOST=$1; shift
ssh -t "$HOST" "sudo systemctl stop emulationstation; $*; sudo systemctl start emulationstation"
