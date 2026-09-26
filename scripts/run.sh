#!/usr/bin/env bash
# Stop ES, run a command on the device in the foreground, start ES again.
# scripts/run.sh r36a 'fluidsynth -i -a alsa -m alsa_seq /roms/synth/x.sf2'
#
# The trap matters: Ctrl-C on the -t tty hits the whole remote process group, so
# a plain 'stop; cmd; start' would leave the handheld sitting on a dead console.
set -uo pipefail
HOST=$1; shift
ssh -t "$HOST" "sudo systemctl stop emulationstation
trap 'sudo systemctl start emulationstation' EXIT INT TERM
$*"
