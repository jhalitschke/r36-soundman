#!/usr/bin/env bash
# Ports, cores and ES systems to the device. scripts/deploy.sh [host]
set -euo pipefail
HOST=${1:-r36a}
cd "$(dirname "$0")/.."
OUT=device/$HOST; mkdir -p "$OUT"

echo "== ports"
# build.sh is a host-side script; on the device it would show up as a launchable
# port that tries to git clone on the handheld.
rsync -av --exclude src --exclude build --exclude build.sh ports/ "$HOST:/roms/ports/"
ssh "$HOST" 'chmod +x /roms/ports/*/*.sh'

echo "== cores"
CORES=$(ssh "$HOST" 'grep ^libretro_directory ~/.config/retroarch/retroarch.cfg | cut -d\" -f2')
INFO=$(ssh "$HOST" 'grep ^libretro_info_path ~/.config/retroarch/retroarch.cfg | cut -d\" -f2')
for so in cores/*/*_libretro.so; do
  [ -e "$so" ] || continue
  scp "$so" "$HOST:$CORES/"; scp "${so%.so}.info" "$HOST:$INFO/" || true
done

echo "== es_systems"
# ES reads ~/.emulationstation/es_systems.cfg before /etc, so patch the one it
# actually uses - inventory.sh records the same thing.
ES=$(ssh "$HOST" 'for f in "$HOME"/.emulationstation/es_systems.cfg /etc/emulationstation/es_systems.cfg; do [ -f "$f" ] && { echo "$f"; break; }; done')
[ -n "$ES" ] || { echo "no es_systems.cfg found on $HOST" >&2; exit 1; }
echo "-> $ES"
scp "$HOST:$ES" "$OUT/es_systems.cfg"
# --cores: the directory the .so really went into, instead of letting es-merge
# derive a second one from the device file (which may be the 32-bit RetroArch).
python3 scripts/es-merge.py "$OUT/es_systems.cfg" es/systems/*.xml --cores "$CORES" \
  > "$OUT/es_systems.merged.cfg"
scp "$OUT/es_systems.merged.cfg" "$HOST:/tmp/es_systems.cfg"

# The rom directories come from the fragments, so a new system cannot be
# forgotten here; ES hides a system whose <path> does not exist.
DIRS=$(python3 -c "
import glob, xml.etree.ElementTree as ET
print(' '.join(sorted({ET.parse(f).getroot().findtext('path') for f in glob.glob('es/systems/*.xml')})))")

ssh "$HOST" "
  set -e
  f=$ES; [ -f \$f.orig ] || sudo cp \$f \$f.orig
  sudo cp /tmp/es_systems.cfg \$f
  for d in $DIRS; do sudo mkdir -p \"\$d\"; sudo chown \"\$(id -un):\$(id -gn)\" \"\$d\"; done
  # An empty .wopl is the marker that lets ES launch the adl core on its
  # embedded bank; a real bank dropped next to it takes precedence.
  [ -e /roms/adlib/embedded.wopl ] || : > /roms/adlib/embedded.wopl
  sudo systemctl restart emulationstation"
echo "done. the original is on the device as ${ES}.orig"
