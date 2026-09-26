#!/usr/bin/env bash
# Ubuntu/macOS host: the PC end of the USB cable.
#
#   scripts/usb-net-host.sh [-w SECONDS] [--share] [ifname]
#
# Two directions, and the handheld has to be told the same one:
#
#   default    the handheld serves (10.44.44.1) and this takes 10.44.44.2.
#              It runs a DHCP server too, but a static pair depends on nothing
#              but the wire - and dnsmasq on the device has already been the
#              reason a perfectly good link looked dead.
#   --share    this PC serves and NATs its own connection, so the handheld gets
#              an address from it and reaches the internet. PortMaster and apt
#              need that. On the handheld: "r36-usbnet internet".
#
# Either way the device's address is printed at the end, read out of the ARP
# table by its fixed MAC, because under --share it is whatever DHCP handed out.
#
# The profile is bound to the gadget's MAC, not to an interface name: the kernel
# names the interface after the USB bus path, which changes with the port. The
# MAC is fixed because g_ether is loaded with host_addr - but only RNDIS and ECM
# actually carry it to the host; under EEM or the CDC subset the host invents a
# random one and this will not match.
set -euo pipefail

HOST_MAC=42:61:72:6b:6f:54   # host_addr in tools/r36-usbnet
DEV_MAC=42:61:72:6b:6f:53   # dev_addr, what the handheld's usb0 answers with
HOST_IP=10.44.44.2/24
CON=r36-usb
WAIT=0
SHARE=0

while [ $# -gt 0 ]; do
  case $1 in
    -w|--wait) WAIT=${2:?-w needs seconds}; shift 2 ;;
    --share) SHARE=1; shift ;;
    --files) SHARE=0; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) IF=$1; shift ;;
  esac
done

# Gadget interfaces are found by their driver, not by name: "enx*" names (and
# altnames) also belong to built-in NICs and to RTL8152/8153 dongles, which
# must not be touched.
gadget_ifs() {
  local p drv
  for p in /sys/class/net/*; do
    [ -e "$p/device/driver" ] || continue
    drv=$(basename "$(readlink -f "$p/device/driver")")
    case $drv in rndis_host|cdc_ether|cdc_ncm|cdc_subset|cdc_eem) echo "${p##*/}" ;; esac
  done
}

mac_of() { cat "/sys/class/net/$1/address" 2>/dev/null; }

if lsmod | grep -q '^cdc_subset '; then
  echo "warning: cdc_subset is loaded. It claims the device id 0525:a4a2 wholesale and can" >&2
  echo "         bind the data interface before rndis_host claims it for the RNDIS handshake," >&2
  echo "         which leaves a link that carries nothing. See README, phase 0:" >&2
  echo "           echo 'blacklist cdc_subset' | sudo tee /etc/modprobe.d/r36-no-cdc-subset.conf" >&2
fi

# Recreated rather than edited, so an older version of this script cannot leave
# a stale address or a DHCP setting behind.
nmcli -t -f NAME con show | grep -qx "$CON" && nmcli con delete "$CON" >/dev/null
if [ "$SHARE" = 1 ]; then
  nmcli con add type ethernet con-name "$CON" mac "$HOST_MAC" \
    ipv4.method shared ipv4.never-default yes ipv6.method ignore \
    connection.autoconnect yes connection.autoconnect-priority 10 >/dev/null
  echo "profile '$CON' -> MAC $HOST_MAC, sharing this PC's connection"
  echo "on the handheld: r36-usbnet internet"
else
  nmcli con add type ethernet con-name "$CON" mac "$HOST_MAC" \
    ipv4.method manual ipv4.addresses "$HOST_IP" ipv4.never-default yes ipv6.method ignore \
    connection.autoconnect yes connection.autoconnect-priority 10 >/dev/null
  echo "profile '$CON' -> MAC $HOST_MAC, $HOST_IP"
fi

deadline=$(( $(date +%s) + WAIT ))
while :; do
  if [ -n "${IF:-}" ]; then
    [ -e "/sys/class/net/$IF" ] && break
  else
    for c in $(gadget_ifs); do
      [ "$(mac_of "$c")" = "$HOST_MAC" ] && { IF=$c; break; }
    done
    [ -n "${IF:-}" ] && break
    for c in $(gadget_ifs); do FALLBACK=$c; done
  fi
  [ "$(date +%s)" -lt "$deadline" ] || break
  sleep 1
done

if [ -z "${IF:-}" ]; then
  echo "no gadget interface with MAC $HOST_MAC." >&2
  if [ -n "${FALLBACK:-}" ]; then
    echo "found $FALLBACK ($(mac_of "$FALLBACK")) - a gadget, but with a MAC of its own, so it is" >&2
    echo "running EEM or the CDC subset rather than RNDIS. Replug the cable." >&2
  else
    echo "nothing plugged in, or the gadget is not up:" >&2
    echo "  boot the handheld, THEN plug the cable into a hub - a root port will not enumerate it," >&2
    echo "  and a module reload on the device is not a reconnect, only the cable is." >&2
    for p in /sys/class/net/*; do
      [ -e "$p/device/driver" ] && printf '  %-18s %s\n' "${p##*/}" "$(basename "$(readlink -f "$p/device/driver")")"
    done >&2
  fi
  exit 1
fi

nmcli device connect "$IF" >/dev/null 2>&1 || nmcli con up "$CON" >/dev/null
echo "$IF up, $(ip -4 -br addr show "$IF" | awk '{print $3}')"

# Where the handheld is depends on who is serving. Broadcast pings are no help -
# most hosts ignore them - so ask the source that actually knows.
if [ "$SHARE" = 1 ]; then
  # NetworkManager's dnsmasq for a shared connection writes its leases here
  LEASES=/var/lib/NetworkManager/dnsmasq-$IF.leases
  DEV=$(awk -v m="$DEV_MAC" 'tolower($2)==m {print $3}' "$LEASES" 2>/dev/null | tail -1)
  [ -n "$DEV" ] || echo "no lease yet in $LEASES - run 'r36-usbnet internet' on the handheld"
else
  DEV=10.44.44.1   # where r36-usbnet puts it when the handheld serves
  ping -c 2 -W 2 "$DEV" >/dev/null 2>&1 || {
    echo "$DEV does not answer - is the gadget up on its side?"
    DEV=""
  }
fi
if [ -n "$DEV" ]; then
  echo "handheld at $DEV -> ssh ark@$DEV"
  [ "$DEV" = "10.44.44.1" ] && echo "  (which is what ssh/config.example calls r36a)"
fi
