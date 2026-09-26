#!/bin/bash
# Switch the OTG port between device and host role, which on this board is a
# choice between the USB-C network cable and anything plugged into a hub.
#
# The two DTBs on BOOT differ only in dr_mode. "peripheral" forces the gadget
# role, which is the only way this board becomes a USB device at all - its ID
# pin decides nothing. "otg" then leaves it a host in practice, which is what a
# MIDI keyboard or an ethernet adapter needs. /boot is mounted rw, so the switch
# is a line in boot.ini and a reboot.
CURR_TTY=/dev/tty1
sudo chmod 666 "$CURR_TTY" 2>/dev/null
printf "\033c" > "$CURR_TTY"
export TERM=linux
export XDG_RUNTIME_DIR=/run/user/$UID/

sudo chmod 666 /dev/uinput 2>/dev/null
export SDL_GAMECONTROLLERCONFIG_FILE=/opt/inttools/gamecontrollerdb.txt
pgrep -f gptokeyb | sudo xargs -r kill -9 2>/dev/null
/opt/inttools/gptokeyb -1 "Boot Role.sh" -c /opt/inttools/keys.gptk >/dev/null 2>&1 &
cleanup() {
  printf "\033c" > "$CURR_TTY"
  pgrep -f gptokeyb | sudo xargs -r kill -9 2>/dev/null
}
trap cleanup EXIT

INI=/boot/boot.ini
DEVICE_DTB=rk3326-r36sPlus-linux.dtb   # dr_mode=peripheral -> USB-C networking
HOST_DTB=gameconsole_linux.dtb         # dr_mode=otg        -> hub, MIDI, ethernet

now=$(grep -oE '[a-zA-Z0-9_.-]+\.dtb' "$INI" | tail -1)
case "$now" in
  "$DEVICE_DTB") role="DEVICE (USB-C networking)"; other=$HOST_DTB; otherrole="HOST (hub, MIDI)" ;;
  "$HOST_DTB")   role="HOST (hub, MIDI)";          other=$DEVICE_DTB; otherrole="DEVICE (USB-C networking)" ;;
  *)             role="unknown ($now)";            other=$DEVICE_DTB; otherrole="DEVICE (USB-C networking)" ;;
esac

dialog --backtitle "Boot Role" --title " OTG port role " --yesno \
  "Now: $role\n\nSwitch to:\n$otherrole\n\nThis rewrites boot.ini and reboots.\nboot.ini.orig is kept." \
  14 46 > "$CURR_TTY" || exit 0

sudo cp -n "$INI" "$INI.orig"
sudo sed -i "s/[a-zA-Z0-9_.-]*\.dtb/$other/" "$INI"
sync
new=$(grep -oE '[a-zA-Z0-9_.-]+\.dtb' "$INI" | tail -1)
if [ "$new" != "$other" ]; then
  dialog --backtitle "Boot Role" --timeout 60 --msgbox \
    "FAILED - boot.ini still says $new.\nNothing changed." 8 46 > "$CURR_TTY"
  exit 1
fi

dialog --backtitle "Boot Role" --timeout 30 --msgbox \
  "boot.ini -> $new\n\nRebooting into:\n$otherrole" 11 46 > "$CURR_TTY"
sudo reboot
