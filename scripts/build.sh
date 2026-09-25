#!/usr/bin/env bash
# arm64-Builds im Docker-Container. Einmalig auf Ubuntu: sudo apt install qemu-user-static binfmt-support
# scripts/build.sh            -> alle Targets
# scripts/build.sh adl        -> nur Core
# scripts/build.sh picoloop   -> nur Port
set -euo pipefail
cd "$(dirname "$0")/.."
UBUNTU=${UBUNTU:-20.04}   # an lsb_release des Geräts anpassen (device/<host>/inventory.txt)
docker build --platform linux/arm64 --build-arg UBUNTU=$UBUNTU -t r36s-build docker/
run() { docker run --rm --platform linux/arm64 -v "$PWD:/src" -w /src r36s-build bash -c "$1"; }
case "${1:-all}" in
  adl|all)      run "make -C cores/adl" ;;&
  picoloop|all) run "ports/picoloop/build.sh" ;;
esac
