#!/usr/bin/env bash
# Phase 2: audio/MIDI diagnostics. scripts/diag.sh [host] [seq-port]  (e.g. 20:0 -> dump 5 s of events)
set -uo pipefail
HOST=${1:-r36a}; PORT=${2:-}
ssh "$HOST" bash -s "$PORT" <<'REMOTE'
PORT=$1
echo "== aplay -l";    aplay -l
echo "== amidi -l";    amidi -l
echo "== aseqdump -l"; aseqdump -l
echo "== rawmidi";     ls -l /dev/snd/midi* 2>/dev/null || echo "no rawmidi device"
if [ -n "$PORT" ]; then echo "== aseqdump -p $PORT (5 s, press keys now)"; timeout 5 aseqdump -p "$PORT"; fi
REMOTE
