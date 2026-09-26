#!/bin/bash
# Dumps everything needed to tell apart "no UDC", "UDC but no host session" and
# "enumerated" - and whether the booted devicetree really has the patched
# otg-port. Writes to /roms so the file can be read from a card reader; there is
# no network yet, which is the whole problem.
OUT=/roms/usbnet-diag.txt

CURR_TTY=/dev/tty1
sudo chmod 666 "$CURR_TTY" 2>/dev/null
export TERM=linux
export XDG_RUNTIME_DIR=/run/user/$UID/

# Without gptokeyb the gamepad produces no key events at all, so dialog can
# never be answered and the only way out is the power switch.
sudo chmod 666 /dev/uinput 2>/dev/null
export SDL_GAMECONTROLLERCONFIG_FILE=/opt/inttools/gamecontrollerdb.txt
pgrep -f gptokeyb | sudo xargs -r kill -9 2>/dev/null
/opt/inttools/gptokeyb -1 "USB Diag.sh" -c /opt/inttools/keys.gptk >/dev/null 2>&1 &

cleanup() {
  printf "\033c" > "$CURR_TTY"
  pgrep -f gptokeyb | sudo xargs -r kill -9 2>/dev/null
}
trap cleanup EXIT

{
echo "== usb gadget diagnostics, $(date -Iseconds)"
echo "model:  $(tr -d '\0' < /sys/firmware/devicetree/base/model 2>/dev/null)"
echo "kernel: $(uname -a)"

echo
echo "== booted devicetree (is the patch live?)"
for n in /proc/device-tree/syscon@*/usb2-phy@*/otg-port /proc/device-tree/syscon@*/usb2-phy@*/host-port; do
  [ -d "$n" ] || continue
  echo "  $n"
  echo "    status  = $(tr -d '\0' < "$n/status" 2>/dev/null)"
done
for n in /proc/device-tree/usb@*; do
  [ -d "$n" ] || continue
  echo "  $n"
  echo "    dr_mode = $(tr -d '\0' < "$n/dr_mode" 2>/dev/null)"
  echo "    status  = $(tr -d '\0' < "$n/status" 2>/dev/null)"
done

echo
echo "== UDC (the authority on whether a host is attached)"
if [ -n "$(ls /sys/class/udc/ 2>/dev/null)" ]; then
  for u in /sys/class/udc/*; do
    echo "  $(basename "$u")"
    for f in state function current_speed maximum_speed is_a_peripheral soft_connect srp; do
      [ -r "$u/$f" ] && echo "    $f = $(cat "$u/$f" 2>/dev/null)"
    done
  done
else
  echo "  NONE - dwc2 registered no gadget controller"
fi

echo
echo "== dwc2 platform device (looking for a force-mode knob)"
for d in /sys/devices/platform/*.usb /sys/devices/platform/ff300000.usb; do
  [ -d "$d" ] || continue
  echo "  $d"
  ls "$d" 2>/dev/null | tr '\n' ' ' | fold -sw 90 | sed 's/^/    /'
  for f in "$d"/*mode* "$d"/*otg*; do
    [ -f "$f" ] && echo "    $(basename "$f") = $(cat "$f" 2>/dev/null)"
  done
done
echo "-- usb2phy sysfs"
for d in /sys/devices/platform/*syscon*/*usb2-phy* /sys/bus/platform/devices/*usb2-phy*; do
  [ -d "$d" ] || continue
  echo "  $d"
  ls "$d" 2>/dev/null | tr '\n' ' ' | fold -sw 90 | sed 's/^/    /'
done

echo
echo "== modules / interface"
lsmod | grep -E 'g_ether|u_ether|libcomposite|usb_f_|dwc2' || echo "  (no gadget module loaded)"
ip -d link show usb0 2>&1 | sed 's/^/  /'
ip -4 addr show usb0 2>&1 | sed 's/^/  /'
echo "-- neighbours on usb0 (does the PC answer?)"
ip neigh show dev usb0 2>&1 | sed 's/^/  /'
echo "-- dnsmasq leases"
cat /tmp/usbnet.leases 2>/dev/null | sed 's/^/  /' || echo "  (no lease file)"

echo
echo "== extcon (unreliable, for info)"
for e in /sys/class/extcon/*; do
  [ -e "$e/state" ] && { echo "  $(basename "$e") ($(cat "$e/name" 2>/dev/null))"; sed 's/^/    /' "$e/state"; }
done

echo
echo "== compat report from option 1, if it ran this boot"
cat /tmp/usbnet-compat.txt 2>/dev/null | sed 's/^/  /' || echo "  (not present)"

echo
echo "== dmesg: dwc2 / phy / usb"
sudo dmesg 2>/dev/null | grep -iE 'dwc2|usb2.?phy|rockchip.*phy|udc|gadget|g_ether|vbus|extcon' | tail -60 | sed 's/^/  /'
echo "-- dmesg tail"
sudo dmesg 2>/dev/null | tail -25 | sed 's/^/  /'
} > "$OUT" 2>&1

sync
# --timeout so a broken gamepad mapping can never wedge the device again
dialog --backtitle "USB Diag" --timeout 180 --msgbox \
  "Written to:\n\n$OUT\n\nPower off, put the card in a PC and read\nit from the ROMs partition." 11 46 > "$CURR_TTY"
