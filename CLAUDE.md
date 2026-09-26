# CLAUDE.md – r36-soundman

Synths, trackers and MIDI on the R36S handheld (RK3326, ArkOS). Goal: instruments sit next to C64 and
Amiga in EmulationStation as equals – as ES systems (track A) and as libretro cores (track B).
Development happens entirely from the host (Ubuntu, macOS as an alternative) over SSH; the handheld
display is only used to verify.

## Hard constraints

- **The CPU budget is fixed.** RK3326 = 4x Cortex-A35 @ ~1.3 GHz. Chip/FM emulation yes, subtractive
  VA barely, DSP emulation (gearmulator and friends) no. Never propose an engine that would not run
  on a Raspberry Pi Zero.
- **YAGNI, the ponytail.dev ladder:** needed? already there? stdlib? a platform feature (PortMaster,
  gptokeyb, ALSA, libretro)? Only then our own code. No frameworks, no abstraction layers "for
  later". A new core is a copy of `cores/adl/` with a different library, not a shared engine
  abstraction.
- **Everything over the USB-C cable.** Wi-Fi dongles did not work, the internal Wi-Fi is unreliable.
  SSH over RNDIS (bootstrap) or USB Ethernet on the OTG hub (target). Never propose anything that
  requires Wi-Fi.
- **ArkOS only.** Rocknix and other CFWs do not come up. Paths are ArkOS paths (`/roms`,
  `/opt/system/Tools/PortMaster`, `~/.config/retroarch/retroarch.cfg`,
  `/etc/emulationstation/es_systems.cfg`).
- **Two devices:** `r36a` (the one we tinker with) and `r36b` (reference, untouched card). Changes go
  to r36a first.

## Device access

- SSH hosts `r36a`/`r36b` from `ssh/config.example`, user `ark`. Before working on a device, run
  `scripts/inventory.sh <host>` – the results in `device/<host>/` are the truth about paths, kernel
  modules and the RetroArch config. Never guess a path, always derive it from
  `device/<host>/inventory.txt` or `es_systems.cfg`.
- `device/` is gitignored (device specific). Do not commit copies of it.
- Never delete or overwrite anything on the device that has not been backed up first. `deploy.sh`
  creates `es_systems.cfg.orig`; touch other system files only with an `.orig` copy in place.
- No `apt upgrade` on the device. Individual packages as arm64 `.deb` matching `lsb_release`, via
  `dpkg -i`.

## Build

- Upstream sources are pinned by revision (`ADL_REV`, `PICOLOOP_REV`): the measured audio levels
  and the tests assert absolute numbers.
- Cross builds only in the Docker container (`docker/Dockerfile`, `scripts/build.sh`), platform
  `linux/arm64`. `UBUNTU` in `scripts/build.sh` has to match the ArkOS base
  (`device/<host>/inventory.txt`, the `lsb_release` line).
- On the host, `make -C cores/adl` may run as a pure compile check (x86); the result does not go to
  the device.
- Binaries and `.so` files are gitignored. Libraries the device does not have are bundled with the
  port (`ports/<name>/lib/`), not installed system wide.

## Conventions

- Ports: one folder under `ports/<name>/`, launch script following the PortMaster pattern
  (`source control.txt`, `get_controls`, `$GPTOKEYB`, log to `log.txt` in the port folder, `$ESUDO
  kill` at the end). Select+Start always quits.
- ES systems: one fragment per system in `es/systems/<name>.xml`. `{{RA}}`/`{{CORES}}`/`{{TAIL}}` as
  placeholders, `scripts/es-merge.py` substitutes them from the device file (`{{TAIL}}` carries the
  device command's own `--config`/`%ROM%`). Logos are in `es/theme/logos/`, but the systems stay on
  `theme="ports"` until the inventory shows which theme is installed.
- Cores: `cores/<name>/` with `<name>_libretro.c`, `Makefile`, `<name>_libretro.info`. 48 kHz,
  60 fps, 320x240 RGB565, MIDI straight from `/dev/snd/midiC*D*` (override `<NAME>_MIDI_DEV`), no
  RetroArch MIDI interface.
- Shell: `set -euo pipefail` in host scripts; device scripts stay `bash` without `-e` (PortMaster
  environment).
- Language for docs, comments and commit messages: English. Commit messages short.

## Status

- Done, untested on hardware: all scripts, ES fragments, port scripts, `cores/adl`.
- `cores/adl` is built on x86 and verified by the harness (`scripts/adl_harness.py`): bank loading,
  notes via FIFO, pitch, note-off -> silence, levels. Runs in CI, with a demo WAV as an artifact.
- Open: the makefile name in the picoloop repo (`ports/picoloop/build.sh` lists the candidates), the
  `LGPT_BIN` path (`ports/lgpt/lgpt.sh`), getting an arm64 `gme_libretro.so` (`cores/gme/`), theme
  logos.
- Next engines after `adl`: `opn` (libOPNMIDI, `.wopn`), `mt32` (mt32emu, ROMs in RetroArch's
  `system/`).

## Order (do not skip)

1. Phase 0: SSH over RNDIS to r36a -> `inventory.sh r36a`
2. Phase 1: USB Ethernet on the OTG hub, if `r8152`/`cdc_ether` are present according to the inventory
3. Phase 2: `diag.sh r36a 20:0` shows MIDI notes
4. Phase 4.1: deploy the FluidSynth system -> measure real latency
5. Phase 4.2/4.3/4.4: GME, picoloop, LGPT
6. Phase 5: `build.sh adl` -> deploy -> `run.sh` with `retroarch -L … --verbose`

The details per phase are in `README.md`. When a device path is unclear: inventory first, then ask,
never guess.
