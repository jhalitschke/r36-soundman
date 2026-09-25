#!/usr/bin/env bash
# Phase 2: Audio/MIDI-Diagnose. scripts/diag.sh [host] [seq-port]  (z.B. 20:0 -> 5s Events dumpen)
set -uo pipefail
HOST=${1:-r36a}; PORT=${2:-}
ssh "$HOST" bash -s "$PORT" <<'REMOTE'
PORT=$1
echo "== aplay -l";    aplay -l
echo "== amidi -l";    amidi -l
echo "== aseqdump -l"; aseqdump -l
echo "== rawmidi";     ls -l /dev/snd/midi* 2>/dev/null || echo "kein rawmidi-Device"
if [ -n "$PORT" ]; then echo "== aseqdump -p $PORT (5s, jetzt Tasten drücken)"; timeout 5 aseqdump -p "$PORT"; fi
REMOTE
