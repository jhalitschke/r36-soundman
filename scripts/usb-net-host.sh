#!/usr/bin/env bash
# Ubuntu-Host: RNDIS/ECM-Interface des Handhelds (192.168.7.1) auf 192.168.7.2 legen.
# Aufruf nach dem Einstecken: scripts/usb-net-host.sh [ifname]
set -euo pipefail
IF=${1:-$(ip -o link | awk -F': ' '/usb0|enx/ {print $2; exit}')}
[ -n "$IF" ] || { echo "kein usb0/enx*-Interface gefunden (USB Network Mode auf dem Gerät an?)"; ip -o link; exit 1; }
nmcli con show r36-usb >/dev/null 2>&1 && nmcli con delete r36-usb
nmcli con add type ethernet ifname "$IF" con-name r36-usb ipv4.method manual ipv4.addresses 192.168.7.2/24 ipv6.method ignore
nmcli con up r36-usb
echo "Interface $IF -> 192.168.7.2, teste: ssh ark@192.168.7.1 (pw: ark)"
