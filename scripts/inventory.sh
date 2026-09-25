#!/usr/bin/env bash
# Phase 0/1: Gerät inventarisieren -> device/<host>/
# inventory.txt wird erst bei Erfolg geschrieben; ein Abbruch zerstört kein gutes Inventar.
set -euo pipefail
HOST=${1:-r36a}
cd "$(dirname "$0")/.."
OUT=device/$HOST; mkdir -p "$OUT"
TMP=$OUT/.inventory.tmp
trap 'rm -f "$TMP"' EXIT

ssh "$HOST" bash -s <<'REMOTE' | tee "$TMP"
echo "== system";   uname -a; lsb_release -a 2>/dev/null; ldd --version | head -1
echo "== sudo"
sudo -n true 2>/dev/null && echo "passwortlos" || echo "braucht Passwort -> deploy.sh haengt (ssh ohne -t)"
echo "== usb-net treiber (r8152/cdc_ether)"
echo "-- module"
ls /lib/modules/"$(uname -r)"/kernel/drivers/net/usb/ 2>/dev/null || echo "(kein modules-dir)"
echo "-- einkompiliert (modules.builtin)"
grep -E 'r8152|cdc_ether|usbnet' /lib/modules/"$(uname -r)"/modules.builtin 2>/dev/null || echo "(nichts / keine modules.builtin)"
echo "-- geladen (lsmod)"
lsmod | grep -E 'r8152|cdc_ether|usbnet|snd_usb_audio' || echo "(keins geladen)"
echo "-- kernel-config"
[ -r /proc/config.gz ] && zcat /proc/config.gz | grep -E 'CONFIG_(USB_RTL8152|USB_NET_CDCETHER|USB_USBNET|SND_USB_AUDIO)=' || echo "(kein /proc/config.gz)"
echo "== emulationstation service"
u=$(systemctl list-unit-files --no-legend --no-pager 2>/dev/null | grep -iE 'emulation|emustation|retro')
[ -n "$u" ] && echo "$u" || echo "(kein passendes Unit -> 'systemctl restart emulationstation' in deploy.sh/run.sh pruefen)"
echo "== es_systems.cfg (ES liest die User-Datei zuerst)"
for f in "$HOME"/.emulationstation/es_systems.cfg /etc/emulationstation/es_systems.cfg; do
  [ -f "$f" ] && echo "vorhanden: $f" || echo "fehlt:     $f"
done
echo "== portmaster"; ls /opt/system/Tools/PortMaster/ 2>/dev/null | head; ls /opt/system/Tools/PortMaster/control.txt 2>/dev/null
echo "== retroarch (64- und 32-bit getrennt)"
for c in "$HOME"/.config/retroarch/retroarch.cfg "$HOME"/.config/retroarch32/retroarch.cfg; do
  [ -f "$c" ] || { echo "fehlt: $c"; continue; }
  echo "-- $c"
  grep -E '^(libretro_directory|libretro_info_path|midi_driver|midi_input|audio_driver|audio_latency)' "$c"
done
echo "== roms"; ls /roms
echo "== alsa"; which aplay amidi aseqdump || echo "alsa-utils fehlt"
REMOTE

# Die wirksame es_systems.cfg holen: User-Datei schlaegt /etc.
ES=$(ssh "$HOST" 'for f in "$HOME"/.emulationstation/es_systems.cfg /etc/emulationstation/es_systems.cfg; do [ -f "$f" ] && { echo "$f"; break; }; done')
[ -n "$ES" ] || { echo "keine es_systems.cfg auf $HOST gefunden" >&2; exit 1; }
scp "$HOST:$ES" "$OUT/es_systems.cfg"
echo "== es_systems.cfg-Quelle: $ES" >> "$TMP"

mv "$TMP" "$OUT/inventory.txt"
trap - EXIT
echo "-> $OUT/inventory.txt, $OUT/es_systems.cfg (Quelle: $ES)"
