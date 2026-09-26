#!/bin/bash
# Phase 2 without a network: what ALSA sees, and whether notes actually arrive.
#
# In host role the OTG port carries the keyboard instead of the network cable,
# so there is no ssh to watch this from. Everything goes to /roms, which a card
# reader can get at - and which survives the switch back to device role.
OUT=/roms/midi-diag.txt

CURR_TTY=/dev/tty1
sudo chmod 666 "$CURR_TTY" 2>/dev/null
printf "\033c" > "$CURR_TTY"
export TERM=linux
export XDG_RUNTIME_DIR=/run/user/$UID/

sudo chmod 666 /dev/uinput 2>/dev/null
export SDL_GAMECONTROLLERCONFIG_FILE=/opt/inttools/gamecontrollerdb.txt
pgrep -f gptokeyb | sudo xargs -r kill -9 2>/dev/null
/opt/inttools/gptokeyb -1 "MIDI Diag.sh" -c /opt/inttools/keys.gptk >/dev/null 2>&1 &
cleanup() {
  printf "\033c" > "$CURR_TTY"
  pgrep -f gptokeyb | sudo xargs -r kill -9 2>/dev/null
}
trap cleanup EXIT

busy() { dialog --backtitle "MIDI Diag" --infobox "$1" 5 46 > "$CURR_TTY"; }

busy "Looking at USB and ALSA..."
{
echo "== midi diagnostics, $(date -Iseconds)"
echo "-- devicetree role"
for n in /proc/device-tree/usb@*; do
  [ -d "$n" ] && echo "   $(basename "$n") dr_mode=$(tr -d '\0' < "$n/dr_mode" 2>/dev/null)"
done
echo
echo "-- usb devices (no lsusb on this image)"
for d in /sys/bus/usb/devices/*; do
  [ -f "$d/idVendor" ] || continue
  printf '   %-10s %s:%s  %s %s\n' "$(basename "$d")" "$(cat "$d/idVendor")" \
    "$(cat "$d/idProduct")" "$(cat "$d/manufacturer" 2>/dev/null)" "$(cat "$d/product" 2>/dev/null)"
done
echo
echo "-- aplay -l";    aplay -l 2>&1
echo "-- amidi -l";    amidi -l 2>&1
echo "-- aseqdump -l"; aseqdump -l 2>&1
echo "-- /dev/snd";    ls -l /dev/snd/ 2>&1
echo "-- cards";       cat /proc/asound/cards 2>&1
echo
echo "-- dmesg: usb / audio / midi"
sudo dmesg 2>/dev/null | grep -iE 'usb|snd|midi|audio|dwc2' | tail -40
} > "$OUT" 2>&1
sync

# The interesting port is the first one that is neither the timer/announce pair
# nor the Midi Through loopback.
PORT=$(aseqdump -l 2>/dev/null | awk '$1 ~ /^[0-9]+:[0-9]+$/ && $1 !~ /^(0|14):/ {print $1; exit}')

if [ -z "$PORT" ]; then
  {
  echo
  echo "== NO MIDI PORT FOUND"
  echo "   Only the system ports and Midi Through are there, so nothing is"
  echo "   attached or the port is not in host role."
  } >> "$OUT"
  sync
  dialog --backtitle "MIDI Diag" --timeout 120 --msgbox \
    "No MIDI port.\n\nOnly System and Midi Through.\n\nIs the keyboard on the OTG port, and\nis the board booted in HOST role?\n(Boot Role.sh)\n\nDetails: $OUT" 14 46 > "$CURR_TTY"
  exit 1
fi

dialog --backtitle "MIDI Diag" --infobox \
  "Found $PORT\n\nPLAY SOME NOTES NOW - 15 seconds." 7 46 > "$CURR_TTY"
{
echo
echo "== aseqdump -p $PORT, 15 s"
timeout 15 aseqdump -p "$PORT" 2>&1
} >> "$OUT"
sync

EVENTS=$(grep -ciE 'note on|note off|control change' "$OUT")
dialog --backtitle "MIDI Diag" --timeout 180 --msgbox \
  "Port $PORT\n\nEvents captured: $EVENTS\n\n$( [ "$EVENTS" -gt 0 ] && echo 'MIDI ARRIVES.' || echo 'Nothing came in.')\n\nDetails: $OUT" 13 46 > "$CURR_TTY"
