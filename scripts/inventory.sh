#!/usr/bin/env bash
# Phase 0/1: inventory a device -> device/<host>/
# inventory.txt is only written on success, so an abort never destroys a good inventory.
set -euo pipefail
HOST=${1:-r36a}
cd "$(dirname "$0")/.."
OUT=device/$HOST; mkdir -p "$OUT"
TMP=$OUT/.inventory.tmp
trap 'rm -f "$TMP"' EXIT

ssh "$HOST" bash -s <<'REMOTE' | tee "$TMP"
echo "== system";   uname -a; lsb_release -a 2>/dev/null; ldd --version | head -1
echo "== sudo"
sudo -n true 2>/dev/null && echo "passwordless" || echo "needs a password -> deploy.sh will hang (ssh without -t)"
echo "== usb-net drivers (r8152/cdc_ether)"
echo "-- modules"
ls /lib/modules/"$(uname -r)"/kernel/drivers/net/usb/ 2>/dev/null || echo "(no modules dir)"
echo "-- built in (modules.builtin)"
grep -E 'r8152|cdc_ether|usbnet' /lib/modules/"$(uname -r)"/modules.builtin 2>/dev/null || echo "(nothing / no modules.builtin)"
echo "-- loaded (lsmod)"
lsmod | grep -E 'r8152|cdc_ether|usbnet|snd_usb_audio' || echo "(none loaded)"
echo "-- kernel config"
[ -r /proc/config.gz ] && zcat /proc/config.gz | grep -E 'CONFIG_(USB_RTL8152|USB_NET_CDCETHER|USB_USBNET|SND_USB_AUDIO)=' || echo "(no /proc/config.gz)"
echo "== emulationstation service"
u=$(systemctl list-unit-files --no-legend --no-pager 2>/dev/null | grep -iE 'emulation|emustation|retro')
[ -n "$u" ] && echo "$u" || echo "(no matching unit -> check 'systemctl restart emulationstation' in deploy.sh/run.sh)"
echo "== es_systems.cfg (ES reads the user file first)"
for f in "$HOME"/.emulationstation/es_systems.cfg /etc/emulationstation/es_systems.cfg; do
  [ -f "$f" ] && echo "present: $f" || echo "missing: $f"
done
echo "== portmaster"; ls /opt/system/Tools/PortMaster/ 2>/dev/null | head; ls /opt/system/Tools/PortMaster/control.txt 2>/dev/null
echo "== retroarch (64 and 32 bit are separate)"
for c in "$HOME"/.config/retroarch/retroarch.cfg "$HOME"/.config/retroarch32/retroarch.cfg; do
  [ -f "$c" ] || { echo "missing: $c"; continue; }
  echo "-- $c"
  grep -E '^(libretro_directory|libretro_info_path|midi_driver|midi_input|audio_driver|audio_latency)' "$c"
done
echo "== roms"; ls /roms
echo "== alsa"; which aplay amidi aseqdump || echo "alsa-utils missing"
REMOTE

# Fetch the effective es_systems.cfg: the user file wins over /etc.
ES=$(ssh "$HOST" 'for f in "$HOME"/.emulationstation/es_systems.cfg /etc/emulationstation/es_systems.cfg; do [ -f "$f" ] && { echo "$f"; break; }; done')
[ -n "$ES" ] || { echo "no es_systems.cfg found on $HOST" >&2; exit 1; }
scp "$HOST:$ES" "$OUT/es_systems.cfg"
echo "== es_systems.cfg source: $ES" >> "$TMP"

mv "$TMP" "$OUT/inventory.txt"
trap - EXIT
echo "-> $OUT/inventory.txt, $OUT/es_systems.cfg (source: $ES)"
