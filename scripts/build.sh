#!/usr/bin/env bash
# arm64 builds in the Docker container. One-time on Ubuntu: sudo apt install qemu-user-static binfmt-support
# scripts/build.sh            -> all targets
# scripts/build.sh adl        -> one core (adl, opn)
# scripts/build.sh picoloop   -> port only
set -euo pipefail
cd "$(dirname "$0")/.."
# The container's release does not have to match the device's - only the glibc
# symbol versions the linker binds have to be ones the device can serve. That is
# checked at the end rather than assumed here, because it is the thing that
# actually breaks: a core built too new fails at load with a GLIBC_x.y not found.
UBUNTU=${UBUNTU:-20.04}
GLIBC_MAX=${GLIBC_MAX:-2.30}   # r36a: Ubuntu 19.10, libc-2.30 (device/<host>/inventory.txt)
# The target is checked before the case, not inside it: the branches fall
# through with ;;& so that "all" reaches every one of them, and a catch-all
# arm would then be reached by every single target as well.
TARGET=${1:-all}
case $TARGET in
  adl|opn|picoloop|all) ;;
  *) echo "unknown target: $TARGET (adl, opn, picoloop, all)" >&2; exit 2 ;;
esac

docker build --platform linux/arm64 --build-arg UBUNTU="$UBUNTU" -t r36s-build docker/
# --user: without it everything the build writes into the bind mount is
# root-owned and the host-side "make -C cores/adl" check then fails.
run() { docker run --rm --platform linux/arm64 --user "$(id -u):$(id -g)" -e HOME=/tmp \
          -v "$PWD:/src" -w /src r36s-build bash -c "$1"; }
case $TARGET in
  adl|all)      run "make -C cores/adl" ;;&
  opn|all)      run "make -C cores/opn" ;;&
  picoloop|all) run "ports/picoloop/build.sh" ;;
esac

# Everything that was just built, against what the device can load.
mapfile -t built < <(find cores ports -name '*_libretro.so' -o -name 'picoloop' -type f 2>/dev/null)
if [ ${#built[@]} -gt 0 ]; then
  echo "== glibc (device serves up to $GLIBC_MAX)"
  scripts/glibc-check.py --max "$GLIBC_MAX" "${built[@]}"
fi
