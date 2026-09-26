#!/usr/bin/env bash
# Ports, cores and ES systems to the device. scripts/deploy.sh [host]
set -euo pipefail
HOST=${1:-r36a}
cd "$(dirname "$0")/.."
OUT=device/$HOST; mkdir -p "$OUT"

echo "== ports"
rsync -av --exclude src --exclude build ports/ "$HOST:/roms/ports/"
ssh "$HOST" 'chmod +x /roms/ports/*/*.sh'

echo "== cores"
CORES=$(ssh "$HOST" 'grep ^libretro_directory ~/.config/retroarch/retroarch.cfg | cut -d\" -f2')
INFO=$(ssh "$HOST" 'grep ^libretro_info_path ~/.config/retroarch/retroarch.cfg | cut -d\" -f2')
for so in cores/*/*_libretro.so; do
  [ -e "$so" ] || continue
  scp "$so" "$HOST:$CORES/"; scp "${so%.so}.info" "$HOST:$INFO/" || true
done

echo "== es_systems"
scp "$HOST:/etc/emulationstation/es_systems.cfg" "$OUT/es_systems.cfg"
python3 scripts/es-merge.py "$OUT/es_systems.cfg" es/systems/*.xml > "$OUT/es_systems.merged.cfg"
scp "$OUT/es_systems.merged.cfg" "$HOST:/tmp/es_systems.cfg"
ssh "$HOST" 'f=/etc/emulationstation/es_systems.cfg; [ -f $f.orig ] || sudo cp $f $f.orig; sudo cp /tmp/es_systems.cfg $f; for d in synth chiptune adlib lgpt; do sudo mkdir -p /roms/$d; sudo chown ark:ark /roms/$d; done; sudo systemctl restart emulationstation'
echo "done. the original is on the device as es_systems.cfg.orig"
