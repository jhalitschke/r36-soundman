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

- SSH hosts `r36a`/`r36b` from `ssh/config.example`, user `ark`, at 10.44.44.1 while the USB gadget is
  up. With no cable yet, the SD card in a host reader is the inventory source (see
  `device/r36a/card-inventory.txt`); mount its root partition read-only. Before working on a device,
  run `scripts/inventory.sh <host>` – the results in `device/<host>/` are the truth about paths, kernel
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
  `linux/arm64`. The container's Ubuntu does **not** have to match the device's: what matters is the
  symbol versions the linker binds, and `scripts/build.sh` checks those with `scripts/glibc-check.py`
  at the end of every build. Measured on adl from a 20.04 container against r36a's 19.10: the highest
  is `GLIBC_2.29` and `GLIBCXX_3.4.21`, well inside the device's 2.30 and 3.4.28.
- On the host, `make -C cores/adl` may run as a pure compile check (x86); the result does not go to
  the device.
- Binaries and `.so` files are gitignored. Libraries the device does not have are bundled with the
  port (`ports/<name>/lib/`), not installed system wide.

## Conventions

- Device-side scripts for the ES Options menu live in `tools/` and are copied to the card's
  `EASYROMS/tools/` (that is `/roms/tools/` on the device). They write their output under `/roms/`, so
  it can be read from a card reader while there is no network.
- Ports: one folder under `ports/<name>/`, launch script following the PortMaster pattern
  (`source control.txt`, `get_controls`, `$GPTOKEYB`, log to `log.txt` in the port folder, `$ESUDO
  kill` at the end). Select+Start always quits.
- ES systems: one fragment per system in `es/systems/<name>.xml`. `{{RA}}`/`{{CORES}}`/`{{APPEND}}`/
  `{{TAIL}}` as placeholders, `scripts/es-merge.py` substitutes them from the device file (`{{TAIL}}`
  carries the device command's own `--config`/`%ROM%`). `<theme>` is the system's own name, which is
  what the installed theme looks a logo up by: r36a runs **gameconsole-sagabox**, which takes them as
  `_art/logos/${system.theme}.png`. `deploy.sh` copies `es/theme/logos/*.png` into whichever ThemeSet
  is switched on, never over one the theme ships itself - so switching themes means deploying again.
  A system needs no folder of its own in the theme: 11 of ArkOS's own have none and ES copes.
- Cores: `cores/<name>/` with `<name>_libretro.c`, `Makefile`, `<name>_libretro.info`. 48 kHz,
  60 fps, 320x240 RGB565, MIDI straight from `/dev/snd/midiC*D*` (override `<NAME>_MIDI_DEV`), no
  RetroArch MIDI interface.
- Shell: `set -euo pipefail` in host scripts; device scripts stay `bash` without `-e` (PortMaster
  environment).
- Language for docs, comments and commit messages: English. Commit messages short.

## Status

- Nothing has run on hardware yet, but r36a's card has been read on the host, so the device facts
  below are measured rather than guessed (`device/r36a/card-inventory.txt`): ArkOS on **Ubuntu 19.10
  eoan, glibc 2.30, kernel 4.4.189**; `es_systems.cfg` only in `/etc/emulationstation/`;
  `libretro_directory = ~/.config/retroarch/cores` (and a separate `retroarch32`);
  `system_directory = /roms/bios`; `audio_latency 128`, `midi_input OFF`. Already installed:
  `fluidsynth`, `dialog`, `dnsmasq`, `dhclient`, `filebrowser`, `smbd`, `aplay`/`amidi`/`aseqdump`/
  `amixer`, `retroarch` + `retroarch32`, `/opt/inttools/gptokeyb` + `keys.gptk`.
- **Phase 0 works.** `ssh r36a` is passwordless, `scripts/inventory.sh r36a` has run, and
  `device/r36a/inventory.txt` is the truth from here on. It took four fixes stacked on each other,
  all of which look like a bad cable from the outside: the PHY's `otg-port` was `disabled` while
  dwc2's `phys` pointed at it; `dr_mode` had to go from `otg` to `peripheral` because the ID pin
  decides nothing on this board; the laptop's xHCI *root port* never enumerates the gadget while a
  hub does it first try; and `cdc_subset` claims `0525:a4a2` wholesale and squats on the data
  interface of the RNDIS configuration, locking `rndis_host` out of the handshake
  (`modprobe -r cdc_subset`, then replug). Ignore `extcon` here, it lies; the UDC state and the
  *host's* `dmesg` are the authorities.
- A module reload on the device does not re-enumerate on the host: dwc2 keeps the D+ pull-up up when
  the UDC is unbound, so the PC keeps talking to a gadget that is gone (rx_errors climbing, `I/O
  error` on any control transfer). Only unplugging the cable produces the disconnect. Pick one mode,
  set it at boot, replug once - do not build retry loops over modes.
- **The link is durable now.** Device: `tools/r36-usbnet` in `/usr/local/bin` plus its unit, enabled,
  `start ecm`, `KillMode=process` (the default control-group kill takes dnsmasq down with the script
  and looks exactly like a dead link). Host: `blacklist cdc_subset` in `/etc/modprobe.d/`, and the
  `r36-usb` profile with a static 10.44.44.2 bound to the gadget's MAC. Routine: boot, then plug the
  cable into a hub, then `ssh r36a`. Both handles are forced by the hardware, not by us.
- The host binds `rndis_host`, not `cdc_ether`, even with ECM offered as config 1:
  `usb_choose_configuration()` prefers an RNDIS config whenever `rndis_host` exists. A gadget with no
  RNDIS config (`g_ncm`, or configfs) would be needed to change that, and there is no reason to -
  `rx_errors` 0 and 0.5 ms as it stands.
- Prepared on the card: `USB Network Mode.sh` from
  ctgl1987/arkos-usb-network-mode is in `EASYROMS/tools/`, and both DTBs that `boot.ini`/`boot01.ini`
  name are patched with `scripts/dtb-otg.py` (`.orig` next to them). The address is **10.44.44.1**
  with the handheld as DHCP server - the earlier 192.168.7.x was a guess and is gone.
- Cores: `cores/adl` (OPL3) and `cores/opn` (YM2612) are built on x86 and arm64 and driven by the
  harness (`scripts/adl_harness.py`): bank loading, notes via FIFO, pitch, note-off -> silence,
  MIDI wire format, levels, framebuffer. Both run in CI with demo WAVs and screenshots as artifacts.
  `opn` needs a `.wopn` bank - libOPNMIDI has no embedded one.
- picoloop is built for arm64 with the makefile and key mapping settled
  (`Makefile.PatternPlayer_raspi1_RtAudio_sdl20`, RtAudio on ALSA, `keys.gptk` from `Master.h`).
- Logos for every system are in `es/theme/logos/`.
- **ES lists adlib, opn and lgpt** on r36a; chiptune and synth stay hidden until someone puts a
  chiptune and a soundfont in their directories, which is content rather than work.
- Open, and all of it needs hardware someone has to plug in: phase 2 (a MIDI-only, self-powered
  device straight on the port), phase 1 (a plain powered USB 2.0 hub, not a dock), a `.sf2` for
  synth, and whether picoloop and LGPT sound right once a button leaves their first screen.
- **`cores/gme` is built and runs too**, so ES lists adlib, opn and chiptune. It is libretro's Game
  Music Emu at a pinned revision, GPL-3.0 against our MIT, built rather than vendored - the `.so` is
  gitignored so nothing redistributes a binary. It runs at 44100 Hz rather than our 48000, being
  upstream's core and not written to our conventions, so `core_smoke.py` is not aimed at it.
- **`cores/opn` ships a bank**: `Doom32x-fixx.wopn`, MIT and explicitly free to redistribute, with its
  readme beside it. `deploy.sh` places it only when `/roms/opn` has none, so a bank the user drops in
  is never clobbered. `tests/test_shipped_content.py` guards that the licence travels with it.
- **`cores/adl` and `cores/opn` both run on r36a**, and ES shows them in the carousel. `opn` has the
  same symbol profile as `adl` (at most `GLIBC_2.29`, `GLIBCXX_3.4.21`) and the three behaviours
  CLAUDE.md distinguishes it by all hold on the hardware: without content RetroArch refuses before
  loading it (`supports_no_game = false`), an empty file fails loudly
  (`bank: Custom bank: Unexpected ending!`) rather than falling back the way `adl`'s marker does, and
  a real `.wopn` loads with `Gain 4.00`. Bank for the test: `xg.wopn`, whose readme puts it in the
  freely redistributable camp, as does the MIT `Doom32x-fixx.wopn`.
- **`cores/adl` runs on r36a.** Deployed with `deploy.sh`, started with `run.sh`: `ldd` resolves
  every library on the device, the empty `embedded.wopl` selects the embedded bank as designed, the
  AV info comes out at 320x240 / 60 fps / 48 kHz, ALSA takes the output, and 1422 frames went out in
  23 s with 14 dropped - the RK3326 holds 60 fps. Opening MIDI fails cleanly with a retry loop
  ("no rawmidi device"), which is correct: there is no MIDI hardware attached, see phase 2.
- **Audio latency: 85 ms is not the floor, and `audio_latency` is not the knob.** ALSA's `default` on
  ArkOS is a dmix mixer with `period_size 1024` written into its config, so nothing a client asks for
  gets below 2048 frames / 42.7 ms. `audio_device = "plughw:0,0"` goes straight to the card:
  `audio_latency = 16` then gives 768 frames / 16 ms, and 8 ms works too. Below 8 ms it falls apart
  (2 underruns at 5 ms, 8 at 4, 113 at 2). Between 8 and 16 single underruns wander and do not track
  the buffer - 16 ms is a margin choice, not a measured optimum. The cost is exclusive use of the
  card, which costs nothing here since ES is stopped while a core runs.
  Applied to our systems only: `es/retroarch-lowlatency.cfg` is deployed as
  `~/.config/retroarch/r36-lowlatency.cfg` and `{{APPEND}}` in the RetroArch fragments turns into the
  `--appendconfig` for it - 3 of the device's 129 systems, and its `retroarch.cfg` keeps its checksum.
- All of that was measured on **silence** - no MIDI hardware, so the core emits nothing. Underrun
  counts are meaningful, "does it sound clean" is not answered.
- A cross-built .so sits where a host build would, so the core tests check the ELF's architecture and
  skip rather than fail on a dlopen that reports a foreign binary as a missing file.
- **picoloop is built and runs on r36a** (`ports/picoloop/picoloop`, aarch64, with `font.ttf` and
  `font.bmp` beside it). It stays up and exits cleanly but does not open the sound card: its first
  screen is the config page and **A** leaves it, so the audio path needs a button press to confirm.
- **No realtime priority on this device**: `RLIMIT_RTPRIO` is 0 for `ark`, so fluidsynth's
  `Failed to set thread to high priority` is real and unavoidable without changing the system's
  limits. `nice -n -19` does work (it returns -19), so both port scripts now ask for it, as ArkOS's
  own 123 commands do. Not measured yet: the real latency floor, which needs MIDI to create load.
- **The cable can carry internet too**, which is what PortMaster and `apt` need:
  `scripts/usb-net-host.sh --share` on the PC and `r36-usbnet internet` on the handheld. Addressing
  only - the gadget stays loaded, so no replug - and the handheld falls back to serving on 10.44.44.1
  if nothing answers, which makes it safe to run over the link it changes. Measured: 16 ms to
  8.8.8.8, `curl https://github.com` -> 200. Note the handheld is then on a DHCP address, not the
  10.44.44.1 that `ssh/config.example` calls `r36a`.
- Phase 2 is open and blocked on hardware, not software: USB MIDI and the ALSA sequencer are built
  into the kernel, the host role works, but nothing has enumerated yet. A Dell WD19 fails on PD it
  cannot negotiate; a DDJ-FLX4 froze the device even on external power (suspect dwc2's host path with
  isochronous transfers - it is an audio device). The missing test is a MIDI-only, self-powered
  device straight on the port. Note that the internal wifi hangs off the same dwc2 port and is
  dropped whenever anything is plugged in.
- Next engine: `mt32` (mt32emu, ROMs in RetroArch's `system/`).

## Order (do not skip)

Phases 0 and 3 are done, 4.2-4.4 and 5 run on the device. What is left needs hardware: a MIDI-only
self-powered device on the port (phase 2), and a plain powered USB 2.0 hub for phase 1. Everything
else below is history now, kept because the order is still the order for r36b.

1. Phase 0: `USB Network Mode.sh` option 1, then 2 -> `ssh ark@10.44.44.1` -> `inventory.sh r36a`
2. Phase 1: USB Ethernet on a **plain powered USB 2.0 hub** in the host role (`tools/Boot Role.sh`) -
   `r8152`/`cdc_ether`/`ax88179_178a` are on the card. Not a dock: a WD19 fails on PD this port
   cannot negotiate. Host role costs the USB-C network cable, so the hub has to carry the network.
3. Phase 2: `diag.sh r36a 20:0` shows MIDI notes
4. Phase 4.1: deploy the FluidSynth system -> measure real latency
5. Phase 4.2/4.3/4.4: GME, picoloop, LGPT
6. Phase 5: `build.sh adl` -> deploy -> `run.sh` with `retroarch -L … --verbose`

The details per phase are in `README.md`. When a device path is unclear: inventory first, then ask,
never guess.
