#!/usr/bin/env bash
# Phase 0/1: Gerät inventarisieren -> device/<host>/
set -euo pipefail
HOST=${1:-r36a}
cd "$(dirname "$0")/.."
OUT=device/$HOST; mkdir -p "$OUT"
ssh "$HOST" bash -s <<'REMOTE' | tee "$OUT/inventory.txt"
echo "== system";   uname -a; lsb_release -a 2>/dev/null; ldd --version | head -1
echo "== usb-net treiber (r8152/cdc_ether)"
ls /lib/modules/$(uname -r)/kernel/drivers/net/usb/ 2>/dev/null || echo "(kein modules-dir)"
[ -r /proc/config.gz ] && zcat /proc/config.gz | grep -E 'CONFIG_(USB_RTL8152|USB_NET_CDCETHER|USB_USBNET|SND_USB_AUDIO)=' || echo "(kein /proc/config.gz)"
echo "== portmaster"; ls /opt/system/Tools/PortMaster/ 2>/dev/null | head; ls /opt/system/Tools/PortMaster/control.txt 2>/dev/null
echo "== retroarch"; grep -E '^(libretro_directory|libretro_info_path|midi_driver|midi_input|audio_driver|audio_latency)' ~/.config/retroarch/retroarch.cfg
echo "== roms"; ls /roms
echo "== alsa"; which aplay amidi aseqdump || echo "alsa-utils fehlt"
REMOTE
scp "$HOST:/etc/emulationstation/es_systems.cfg" "$OUT/es_systems.cfg"
echo "-> $OUT/inventory.txt, $OUT/es_systems.cfg"
