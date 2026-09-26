#!/bin/bash
# %ROM% = the empty marker file song.lgpt in the project folder; LGPT starts in that folder.
# Point LGPT_BIN at the binary or launch script of the PortMaster port.
LGPT_BIN=${LGPT_BIN:-/roms/ports/LittleGPTracker/lgpt.sh}
cd "$(dirname "$1")" || exit 1
exec "$LGPT_BIN" "$PWD" > /roms/ports/lgpt/log.txt 2>&1
