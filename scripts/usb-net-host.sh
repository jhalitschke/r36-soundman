#!/usr/bin/env bash
# Ubuntu host: bring up the handheld's USB gadget interface and find its address.
#
# The handheld side is "USB Network Mode.sh" (option 2, universal), which runs
# g_ether plus its own dnsmasq: the DEVICE hands out addresses and sits on
# 10.44.44.1, so the host takes DHCP here instead of a static address.
#
#   scripts/usb-net-host.sh            # detect the gadget interface
#   scripts/usb-net-host.sh arkos0     # or name it
set -euo pipefail

DEV_IP=10.44.44.1          # the handheld in universal mode
HOST_FALLBACK=10.44.44.2   # only if the device's DHCP server never answers
CON=r36-usb

# The gadget's drivers. Not r8152/asix - those are the USB Ethernet adapters
# from phase 1, which are a different thing sitting on the OTG hub.
is_gadget() {
  local dev drv
  dev=$(readlink -f "/sys/class/net/$1/device" 2>/dev/null) || return 1
  [ -n "$dev" ] || return 1
  case "$dev" in */usb[0-9]*/*) ;; *) return 1 ;; esac   # must hang off a USB bus
  drv=$(basename "$(readlink -f "/sys/class/net/$1/device/driver" 2>/dev/null || echo none)")
  case "$drv" in rndis_host|cdc_ether|cdc_ncm|cdc_subset) return 0 ;; *) return 1 ;; esac
}

detect() {
  # arkos0 first: upstream's setup-linux.sh pins that name to the gadget's
  # 0525:a4a2 by udev rule, so it is the one name that cannot drift.
  local i
  for i in arkos0 /sys/class/net/*; do
    i=$(basename "$i")
    [ -e "/sys/class/net/$i" ] || continue
    is_gadget "$i" && { echo "$i"; return 0; }
  done
  return 1
}

IF=${1:-$(detect || true)}
if [ -z "$IF" ]; then
  # Never guess here. Matching interface NAMES is what used to pick the wrong
  # one: "ip -o link" prints systemd's "altname enx<mac>" on the same line as
  # the onboard NIC, so a /enx/ match happily returned enp0s31f6 and put the
  # handheld's address on the host's own LAN port.
  echo "no USB gadget interface found." >&2
  echo "The handheld is not in USB Network Mode yet - see phase 0 in README.md." >&2
  echo "" >&2
  echo "USB network interfaces present (should list the handheld):" >&2
  for i in /sys/class/net/*; do
    i=$(basename "$i")
    is_gadget "$i" && echo "  $i" >&2
  done
  exit 1
fi

[ -e "/sys/class/net/$IF" ] || { echo "no such interface: $IF" >&2; exit 1; }
if ! is_gadget "$IF"; then
  echo "$IF is not a USB gadget interface - refusing to reconfigure it." >&2
  echo "Passing the wrong name here takes down the host's own network." >&2
  exit 1
fi
if ip route show default dev "$IF" | grep -q .; then
  echo "$IF carries the host's default route - refusing to touch it." >&2
  exit 1
fi

command -v nmcli >/dev/null || {
  echo "no nmcli. Without NetworkManager: 'sudo dhclient $IF', then ssh ark@$DEV_IP" >&2
  exit 1
}

nmcli con show "$CON" >/dev/null 2>&1 && nmcli con delete "$CON" >/dev/null
# ipv4.method auto: the handheld is the DHCP server, not us.
nmcli con add type ethernet ifname "$IF" con-name "$CON" \
  ipv4.method auto ipv6.method ignore connection.autoconnect yes >/dev/null
nmcli con up "$CON" >/dev/null

# The lease can take a moment; without an address the ssh below just hangs.
for _ in {1..20}; do
  ADDR=$(ip -4 -o addr show dev "$IF" | awk '{print $4; exit}')
  [ -n "$ADDR" ] && break
  sleep 0.5
done

if [ -z "${ADDR:-}" ]; then
  echo "$IF is up but got no lease - falling back to $HOST_FALLBACK/24"
  nmcli con modify "$CON" ipv4.method manual ipv4.addresses "$HOST_FALLBACK/24"
  nmcli con up "$CON" >/dev/null
  ADDR=$(ip -4 -o addr show dev "$IF" | awk '{print $4; exit}')
fi

echo "interface $IF -> ${ADDR:-no address}"
if ping -c 1 -W 2 -I "$IF" "$DEV_IP" >/dev/null 2>&1; then
  echo "handheld answers at $DEV_IP -> ssh ark@$DEV_IP (password: ark)"
else
  echo "no answer from $DEV_IP. On the handheld: USB Network Mode -> option 1 (check),"
  echo "then option 2 (universal). A charge-only cable looks exactly like this."
fi
