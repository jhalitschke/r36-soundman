#!/bin/bash
# Force the Rockchip usb2phy into the peripheral role, then bring the gadget up
# in that order - which is the whole point of this script existing next to
# "USB Network Mode.sh".
#
# dr_mode in the devicetree only settles what dwc2 does. On the RK3326 BSP the
# usb2phy picks its own role and sits on host: extcon reads USB_HOST=1 with
# USB_VBUS_EN=1, so the handheld feeds VBUS into a cable whose other end is a PC
# doing the same, and the gadget enumerates and collapses in a loop ("new device
# is high-speed" every 200 ms). otg_mode is the phy driver's own override, but
# it exists only at runtime, so it has to be set again after every boot - and
# before the gadget binds, because the role is what the gadget binds into.
#
# The module parameters repeat the ones upstream uses on purpose: the host side
# matches the gadget by its fixed MAC, so a different one here would look like a
# different adapter.
OUT=/roms/usbnet-otg.txt
DEV_MAC=42:61:72:6b:6f:53
HOST_MAC=42:61:72:6b:6f:54

CURR_TTY=/dev/tty1
sudo chmod 666 "$CURR_TTY" 2>/dev/null
printf "\033c" > "$CURR_TTY"
export TERM=linux
export XDG_RUNTIME_DIR=/run/user/$UID/

# Without gptokeyb the gamepad produces no key events at all, so dialog can
# never be answered and the only way out is the power switch.
sudo chmod 666 /dev/uinput 2>/dev/null
export SDL_GAMECONTROLLERCONFIG_FILE=/opt/inttools/gamecontrollerdb.txt
pgrep -f gptokeyb | sudo xargs -r kill -9 2>/dev/null
/opt/inttools/gptokeyb -1 "USB Peripheral.sh" -c /opt/inttools/keys.gptk >/dev/null 2>&1 &

cleanup() {
  printf "\033c" > "$CURR_TTY"
  pgrep -f gptokeyb | sudo xargs -r kill -9 2>/dev/null
}
trap cleanup EXIT

busy() { dialog --backtitle "USB Peripheral" --infobox "$1" 5 46 > "$CURR_TTY"; }

# Run a privileged command and append whatever it says to the log. The log is
# on /roms (exfat, uid=1000), so it is written as the user while the command
# itself runs under sudo - keeping the two apart is also what stops the
# redirection from being attempted as root.
run() {
  local out
  out=$("$@" 2>&1)
  [ -n "$out" ] && printf '%s\n' "$out" >> "$OUT"
  return 0
}

phy=""
for d in /sys/devices/platform/*syscon*/*usb2-phy* /sys/bus/platform/devices/*usb2-phy*; do
  [ -e "$d/otg_mode" ] || continue
  phy="$d"
  break
done

extcon_line() { cat /sys/class/extcon/extcon0/state 2>/dev/null | tr '\n' ' '; }
udc_line() {
  for u in /sys/class/udc/*; do
    [ -d "$u" ] && echo "$(basename "$u")=$(cat "$u/state" 2>/dev/null)"
  done
}

{
echo "== otg_mode + gadget bring-up, $(date -Iseconds)"
echo "phy: ${phy:-NONE FOUND}"
echo "-- before"
echo "   otg_mode: $(cat "$phy/otg_mode" 2>/dev/null)"
echo "   extcon:   $(extcon_line)"
echo "   udc:      $(udc_line)"
} > "$OUT" 2>&1

busy "Stopping the gadget..."
sudo kill "$(cat /tmp/dnsmasq-usbnet.pid 2>/dev/null)" 2>/dev/null
sudo rmmod g_ether 2>/dev/null
sleep 1

if [ -n "$phy" ]; then
  busy "Setting otg_mode = peripheral..."
  run sudo sh -c "echo peripheral > '$phy/otg_mode'"
  sleep 2
  {
  echo "-- after otg_mode, gadget still unloaded"
  echo "   otg_mode: $(cat "$phy/otg_mode" 2>/dev/null)"
  echo "   extcon:   $(extcon_line)"
  } >> "$OUT" 2>&1
fi

busy "Loading the gadget..."
run sudo modprobe g_ether dev_addr=$DEV_MAC host_addr=$HOST_MAC \
  iProduct=R36S iManufacturer=ArkOS
sleep 2
sudo ip addr flush dev usb0 2>/dev/null
sudo ip addr add 10.44.44.1/24 dev usb0 2>/dev/null
sudo ip link set usb0 up 2>/dev/null

busy "Starting SSH and DHCP..."
sudo systemctl start ssh 2>/dev/null
sudo rm -f /tmp/usbnet.leases
run sudo dnsmasq --interface=usb0 --bind-interfaces --except-interface=lo \
  --port=0 --dhcp-range=10.44.44.10,10.44.44.100,12h \
  --dhcp-option=3 --dhcp-option=6 \
  --pid-file=/tmp/dnsmasq-usbnet.pid --dhcp-leasefile=/tmp/usbnet.leases \
  --conf-file=/dev/null
sleep 3

{
echo "-- after gadget bound"
echo "   otg_mode: $(cat "$phy/otg_mode" 2>/dev/null)"
echo "   extcon:   $(extcon_line)"
echo "   udc:      $(udc_line)"
echo "   usb0:     $(ip -4 addr show usb0 2>/dev/null | grep -oP 'inet \K[0-9.]+')"
echo "-- dmesg"
sudo dmesg 2>/dev/null | grep -iE 'dwc2|usb2.?phy|udc|gadget|g_ether|vbus' | tail -25
} >> "$OUT" 2>&1
sync

EX=$(extcon_line)
UDC=$(udc_line)
MODE=$(cat "$phy/otg_mode" 2>/dev/null)
# --timeout so a broken gamepad mapping can never wedge the device again
dialog --backtitle "USB Peripheral" --timeout 180 --msgbox \
  "otg_mode = ${MODE:-?}\n\n${EX}\n\nUDC: ${UDC:-none}\n\nWanted: USB_HOST=0, USB=1,\nUDC configured/addressed.\n\nDetails in $OUT" 16 46 > "$CURR_TTY"
