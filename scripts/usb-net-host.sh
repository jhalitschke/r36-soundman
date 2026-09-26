#!/usr/bin/env bash
# Ubuntu host: put 192.168.7.2 on the handheld's RNDIS/ECM interface (device is 192.168.7.1).
# Run after plugging in: scripts/usb-net-host.sh [ifname]
set -euo pipefail
IF=${1:-$(ip -o link | awk -F': ' '/usb0|enx/ {print $2; exit}')}
[ -n "$IF" ] || { echo "no usb0/enx* interface found (is USB Network Mode enabled on the device?)"; ip -o link; exit 1; }
nmcli con show r36-usb >/dev/null 2>&1 && nmcli con delete r36-usb
nmcli con add type ethernet ifname "$IF" con-name r36-usb ipv4.method manual ipv4.addresses 192.168.7.2/24 ipv6.method ignore
nmcli con up r36-usb
echo "interface $IF -> 192.168.7.2, now try: ssh ark@192.168.7.1 (password: ark)"
