#!/usr/bin/env bash
# Ubuntu/macOS host: the PC end of the USB cable.
#
#   scripts/usb-net-host.sh [-w SECONDS] [ifname]
#
# The handheld sits on a fixed 10.44.44.1 and this takes 10.44.44.2. It does run
# a DHCP server, but a static pair depends on nothing but the wire - and dnsmasq
# on the device has already been the reason a perfectly good link looked dead.
#
# The profile is bound to the gadget's MAC, not to an interface name: the kernel
# names the interface after the USB bus path, which changes with the port. The
# MAC is fixed because g_ether is loaded with host_addr - but only RNDIS and ECM
# actually carry it to the host; under EEM or the CDC subset the host invents a
# random one and this will not match.
set -euo pipefail

HOST_MAC=42:61:72:6b:6f:54   # host_addr in tools/r36-usbnet
HOST_IP=10.44.44.2/24
CON=r36-usb
WAIT=0

while [ $# -gt 0 ]; do
  case $1 in
    -w|--wait) WAIT=${2:?-w needs seconds}; shift 2 ;;
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
nmcli con add type ethernet con-name "$CON" mac "$HOST_MAC" \
  ipv4.method manual ipv4.addresses "$HOST_IP" ipv4.never-default yes ipv6.method ignore \
  connection.autoconnect yes connection.autoconnect-priority 10 >/dev/null
echo "profile '$CON' -> MAC $HOST_MAC, $HOST_IP"

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
echo "now: ssh r36a"
