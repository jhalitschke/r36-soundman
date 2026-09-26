#!/usr/bin/env bash
# arm64 builds in the Docker container. One-time on Ubuntu: sudo apt install qemu-user-static binfmt-support
# scripts/build.sh            -> all targets
# scripts/build.sh adl        -> one core (adl, opn)
# scripts/build.sh picoloop   -> port only
set -euo pipefail
cd "$(dirname "$0")/.."
UBUNTU=${UBUNTU:-20.04}   # match the device's lsb_release (device/<host>/inventory.txt)
docker build --platform linux/arm64 --build-arg UBUNTU="$UBUNTU" -t r36s-build docker/
# --user: without it everything the build writes into the bind mount is
# root-owned and the host-side "make -C cores/adl" check then fails.
run() { docker run --rm --platform linux/arm64 --user "$(id -u):$(id -g)" -e HOME=/tmp \
          -v "$PWD:/src" -w /src r36s-build bash -c "$1"; }
case "${1:-all}" in
  adl|all)      run "make -C cores/adl" ;;&
  opn|all)      run "make -C cores/opn" ;;&
  picoloop|all) run "ports/picoloop/build.sh" ;;
  *)            echo "unknown target: $1 (adl, opn, picoloop, all)" >&2; exit 2 ;;
esac
