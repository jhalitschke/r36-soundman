#!/bin/bash
# %ROM% = leere Markerdatei song.lgpt im Projektordner; LGPT startet in diesem Ordner.
# LGPT_BIN auf das Binary/Startscript des PortMaster-Ports zeigen lassen.
LGPT_BIN=${LGPT_BIN:-/roms/ports/LittleGPTracker/lgpt.sh}
cd "$(dirname "$1")" || exit 1
exec "$LGPT_BIN" "$PWD" > /roms/ports/lgpt/log.txt 2>&1
