#!/usr/bin/env bash
# Ubuntu host: bring up the handheld's USB gadget interface and say where it is.
#
#   scripts/usb-net-host.sh [-w SECONDS] [--share] [ifname]
#
# Two directions, and the handheld has to be told the same one:
#
#   default    the handheld serves. It runs g_ether plus its own dnsmasq and
#              sits on 10.44.44.1, so the host takes DHCP; a static 10.44.44.2
#              is the fallback for when no lease arrives, which has happened -
#              dnsmasq on the device died with its service once and looked
#              exactly like a dead cable.
#   --share    this PC serves and NATs its own connection, so the handheld can
#              reach the internet. PortMaster and apt need that. On the
#              handheld: "r36-usbnet internet".
set -euo pipefail

DEV_IP=10.44.44.1            # the handheld when it is the one serving
HOST_FALLBACK=10.44.44.2     # only if its DHCP server never answers
DEV_MAC=42:61:72:6b:6f:53    # dev_addr in tools/r36-usbnet, what usb0 answers with
HOST_MAC=42:61:72:6b:6f:54   # host_addr - only RNDIS and ECM carry it to the host
CON=r36-usb
WAIT=0
SHARE=0

while [ $# -gt 0 ]; do
  case $1 in
    -w|--wait) WAIT=${2:?-w needs seconds}; shift 2 ;;
    --share)   SHARE=1; shift ;;
    --files)   SHARE=0; shift ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *)         IF=$1; shift ;;
  esac
done

# A gadget is one of these drivers *on the USB bus*. Not r8152 or asix: those
# are the USB ethernet adapters from phase 1, a different thing on the OTG hub.
is_gadget() {
  local dev drv
  dev=$(readlink -f "/sys/class/net/$1/device" 2>/dev/null) || return 1
  [ -n "$dev" ] || return 1
  case "$dev" in */usb[0-9]*/*) ;; *) return 1 ;; esac
  drv=$(basename "$(readlink -f "/sys/class/net/$1/device/driver" 2>/dev/null || echo none)")
  case "$drv" in rndis_host|cdc_ether|cdc_ncm|cdc_subset|cdc_eem) return 0 ;; *) return 1 ;; esac
}

detect() {
  # arkos0 first: upstream's setup-linux.sh pins that name to the gadget by
  # udev rule, so it is the one name that cannot drift with the port.
  local i
  for i in arkos0 /sys/class/net/*; do
    i=$(basename "$i")
    [ -e "/sys/class/net/$i" ] || continue
    is_gadget "$i" && { echo "$i"; return 0; }
  done
  return 1
}

if lsmod 2>/dev/null | grep -q '^cdc_subset '; then
  echo "warning: cdc_subset is loaded. It claims the device id 0525:a4a2 wholesale and can bind" >&2
  echo "         the data interface of the RNDIS config before rndis_host claims it for the" >&2
  echo "         handshake, leaving a link that carries nothing. See README, phase 0:" >&2
  echo "           echo 'blacklist cdc_subset' | sudo tee /etc/modprobe.d/r36-no-cdc-subset.conf" >&2
fi

deadline=$(( $(date +%s) + WAIT ))
while [ -z "${IF:-}" ]; do
  IF=$(detect || true)
  [ -n "$IF" ] && break
  [ "$(date +%s)" -lt "$deadline" ] || break
  sleep 1
done

if [ -z "${IF:-}" ]; then
  # Never guess by name here. Matching interface NAMES is what used to pick the
  # wrong one: "ip -o link" prints systemd's "altname enx<mac>" on the same line
  # as the onboard NIC, so a /enx/ match happily returned the host's own LAN
  # port and had the handheld's address put on it.
  echo "no USB gadget interface found." >&2
  echo "The handheld is not presenting one - see phase 0 in README.md. In short:" >&2
  echo "  boot it first, THEN plug the cable in, and into a hub rather than a root port." >&2
  echo "" >&2
  echo "USB network interfaces present:" >&2
  for i in /sys/class/net/*; do
    i=$(basename "$i")
    is_gadget "$i" && echo "  $i" >&2
  done
  exit 1
fi

[ -e "/sys/class/net/$IF" ] || { echo "no such interface: $IF" >&2; exit 1; }
is_gadget "$IF" || {
  echo "$IF is not a USB gadget interface - refusing to reconfigure it." >&2
  echo "Passing the wrong name here takes down the host's own network." >&2
  exit 1
}
if ip route show default dev "$IF" | grep -q .; then
  echo "$IF carries the host's default route - refusing to touch it." >&2
  exit 1
fi

command -v nmcli >/dev/null || {
  echo "no nmcli. Without NetworkManager: 'sudo dhclient $IF', then ssh ark@$DEV_IP" >&2
  exit 1
}

# Recreated rather than edited, so an older run cannot leave a stale address or
# the wrong direction behind. Bound to the interface name, and additionally to
# the MAC when the gadget carries the fixed one - then the profile comes up by
# itself on a replug instead of needing this script again.
MAC=$(cat "/sys/class/net/$IF/address" 2>/dev/null || true)
extra=()
[ "$MAC" = "$HOST_MAC" ] && extra=(802-3-ethernet.mac-address "$HOST_MAC")

nmcli con show "$CON" >/dev/null 2>&1 && nmcli con delete "$CON" >/dev/null
if [ "$SHARE" = 1 ]; then
  nmcli con add type ethernet ifname "$IF" con-name "$CON" "${extra[@]}" \
    ipv4.method shared ipv4.never-default yes ipv6.method ignore \
    connection.autoconnect yes >/dev/null
  nmcli con up "$CON" >/dev/null
  echo "$IF -> sharing this PC's connection. On the handheld: r36-usbnet internet"
else
  # ipv4.method auto: the handheld is the DHCP server, not us.
  nmcli con add type ethernet ifname "$IF" con-name "$CON" "${extra[@]}" \
    ipv4.method auto ipv4.never-default yes ipv6.method ignore \
    connection.autoconnect yes >/dev/null
  nmcli con up "$CON" >/dev/null
  for _ in $(seq 1 20); do
    ADDR=$(ip -4 -o addr show dev "$IF" | awk '{print $4; exit}')
    [ -n "${ADDR:-}" ] && break
    sleep 0.5
  done
  if [ -z "${ADDR:-}" ]; then
    echo "$IF is up but got no lease - falling back to $HOST_FALLBACK/24"
    nmcli con modify "$CON" ipv4.method manual ipv4.addresses "$HOST_FALLBACK/24"
    nmcli con up "$CON" >/dev/null
    ADDR=$(ip -4 -o addr show dev "$IF" | awk '{print $4; exit}')
  fi
  echo "$IF -> ${ADDR:-no address}"
fi

# Where the handheld is depends on who is serving. Broadcast pings are no help,
# most hosts ignore them, so ask the source that actually knows.
if [ "$SHARE" = 1 ]; then
  LEASES=/var/lib/NetworkManager/dnsmasq-$IF.leases
  DEV=$(awk -v m="$DEV_MAC" 'tolower($2)==m {print $3}' "$LEASES" 2>/dev/null | tail -1)
  if [ -n "$DEV" ]; then
    echo "handheld at $DEV -> ssh ark@$DEV"
  else
    echo "no lease yet in $LEASES - run 'r36-usbnet internet' on the handheld"
  fi
elif ping -c 1 -W 2 -I "$IF" "$DEV_IP" >/dev/null 2>&1; then
  echo "handheld answers at $DEV_IP -> ssh r36a"
else
  echo "no answer from $DEV_IP. On the handheld: USB Network Mode -> option 1 (check),"
  echo "then option 2 (universal) - or r36-usbnet, if that is installed. A charge-only"
  echo "cable looks exactly like this, and so does a gadget that was up before the cable."
fi
