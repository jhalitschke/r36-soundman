# r36-soundman

[![ci](https://github.com/jhalitschke/r36-soundman/actions/workflows/ci.yml/badge.svg)](https://github.com/jhalitschke/r36-soundman/actions/workflows/ci.yml)

Synths, trackers and MIDI on the R36S handheld (RK3326, ArkOS) – as EmulationStation systems and as
libretro cores, so instruments sit next to C64 and Amiga in the same carousel. Everything is built,
deployed and tested from the host (Ubuntu, macOS works too) over SSH; the handheld display is only
used to verify.

The device side needs hardware, but the libretro core does not: `scripts/adl_harness.py` drives a
built core without RetroArch and renders its audio to a WAV, so pitch, note-off, levels and MIDI
parsing are verified on the host and in CI.

## Layout

    scripts/      host tools (usb-net-host, inventory, diag, run, build, deploy, adl_harness)
    ssh/          example for ~/.ssh/config (r36a, r36b)
    docker/       arm64 build container
    es/systems/   ES system fragments, merged into the device file by es-merge.py
    ports/        launch scripts following the PortMaster pattern -> /roms/ports/<name>/
    cores/        libretro cores (adl = OPL3 via libADLMIDI)
    tests/        hardware-free tests (ES merge, core API, core audio)
    device/<h>/   per device: inventory + copies of es_systems.cfg (gitignored)

## One-time setup on the host

    sudo apt install rsync docker.io qemu-user-static binfmt-support   # Ubuntu
    cat ssh/config.example >> ~/.ssh/config

macOS: Docker Desktop does arm64 without the qemu package. RNDIS needs HoRNDIS there; CDC-ECM works
natively.

## Phase 0 – SSH over the cable (RNDIS)

1. Handheld: Options -> enable USB Network Mode, USB-C cable to the host.
2. `scripts/usb-net-host.sh` (puts 192.168.7.2/24 on usb0/enx*).
3. `ssh ark@192.168.7.1` (password `ark`), then `ssh-copy-id r36a`.
4. No interface shows up: https://github.com/ctgl1987/arkos-usb-network-mode, option 1 checks whether
   the board can do device mode at all. A NOT SUPPORTED device becomes the reference device.

Check: `scripts/inventory.sh r36a` completes and writes `device/r36a/`. `inventory.txt` is only
written on success (an abort never overwrites a good inventory) and also records: `sudo` behaviour,
the ES systemd unit, both RetroArch configs (64/32 bit), which `es_systems.cfg` is the effective one,
and whether `r8152`/`cdc_ether` exist as a module, built in (`modules.builtin`) or loaded (`lsmod`).

## Phase 1 – Host mode + USB Ethernet on the OTG hub

Look at `== usb-net drivers` in `device/r36a/inventory.txt`: is `r8152`/`cdc_ether` there as a `.ko`,
in `modules.builtin` or in `lsmod`? Then turn RNDIS off, attach the OTG hub with an RTL8152/8153
adapter, set host Ethernet to "Shared to other computers" and point `HostName` in `~/.ssh/config` at
the DHCP address. From then on Ethernet, MIDI and a keyboard hang off the hub at the same time.

Fallback without a driver: deploy over RNDIS, run tests with `nohup ... > log.txt 2>&1 &`, unload the
gadget (script option 5), test MIDI, load the gadget again, read the log.

## Phase 2 – Diagnostics

    scripts/diag.sh r36a          # aplay/amidi/aseqdump -l
    scripts/diag.sh r36a 20:0     # dump 5 s of events from that seq port

If alsa-utils is missing: arm64 `.deb` matching `lsb_release` from ports.ubuntu.com, `scp`,
`sudo dpkg -i`. No sound: `amixer cset name='Playback Path' SPK` (or `HP`).

Check: notes arrive in `aseqdump`. Only then continue.

## Phase 3 – Deploy loop

    scripts/deploy.sh r36a        # ports/ -> /roms/ports, cores -> libretro_directory, merge ES systems, restart ES
    scripts/run.sh r36a '<cmd>'   # stop ES, run the command in the foreground, start ES

Afterwards the original es_systems.cfg is on the device as
`/etc/emulationstation/es_systems.cfg.orig`. `{{RA}}` and `{{CORES}}` in the fragments are derived
from the first RetroArch command in the device file.

## Phase 4 – Track A (ArkOS/ES)

**4.1 synth (FluidSynth, end-to-end test)** – install `fluidsynth` + `libfluidsynth` as arm64 `.deb`,
put a `.sf2` in `/roms/synth/`, deploy. Select+Start quits. Latency: turn `PERIOD`/`COUNT` in the
script (`-z`/`-c`) down until it crackles – that is the device's floor.

**4.2 chiptune (GME core, config only)** – put `gme_libretro.so` (arm64: libretro buildbot or build
libretro/libretro-gme in the container) into `cores/gme/` with its `.info` next to it, deploy.
Content goes to `/roms/chiptune/`.

**4.3 picoloop** – `scripts/build.sh picoloop`. First put the SDL2 Linux makefile into
`ports/picoloop/build.sh` (the script lists the ones it finds) and disable Twytch/Open303/Cursynth in
`Master.h`. The first start asks for the audio device: `default` or `hw:0`.

**4.4 lgpt** – install the port through PortMaster, adjust `LGPT_BIN` in `ports/lgpt/lgpt.sh`. One
empty `song.lgpt` per project folder under `/roms/lgpt/`.

**4.5 theme** – until there are logos of our own, every system uses `theme="ports"`.

## Phase 5 – Track B (libretro core)

    scripts/build.sh adl          # cores/adl/adl_libretro.so (arm64)
    scripts/deploy.sh r36a
    scripts/run.sh r36a 'retroarch -L $(grep ^libretro_directory ~/.config/retroarch/retroarch.cfg | cut -d\" -f2)/adl_libretro.so --verbose'

The core reads `/dev/snd/midiC*D*` itself (override `ADL_MIDI_DEV`), so it does not need a
MIDI-capable RetroArch. Display: green/red = MIDI device open, 16 bars = channel activity.
L/R = program, A = panic. Content is optional (a `.wopl` bank in `/roms/adlib/`), without content it
uses embedded bank 0. The emulator is DOSBox OPL (lighter than Nuked); see `adl_switchEmulator` in
`adl_libretro.c`.

Further engines are a copy of `cores/adl/` with a different library: libOPNMIDI (`opn2_*`, `.wopn`),
mt32emu (ROMs into RetroArch's `system/`).

## Tests & CI

Verifiable without the device, the same steps as in `.github/workflows/ci.yml`:

    for f in scripts/*.sh ports/*/*.sh; do bash -n "$f"; done
    shellcheck --severity=warning scripts/*.sh ports/*/*.sh
    make -C cores/adl                              # x86 compile check (not for the device)
    python3 tests/core_smoke.py cores/adl/adl_libretro.so
    python3 -m unittest discover -s tests          # es-merge.py, ES fragments, core audio

`core_smoke.py` loads the `.so` via ctypes and checks the libretro API, the mandatory symbols,
48 kHz / 60 fps / 320x240, and whether the `.info` matches what the core reports. The audio tests
need the built `.so` and skip themselves otherwise. The arm64 build (`scripts/build.sh adl`) only
runs in CI via *Run workflow* – qemu is too slow for every push. Every CI run uploads
`adl-demo.wav` as an artifact: a change to the core is audible, not just green.

## Harness: hearing the core without RetroArch

`scripts/adl_harness.py` drives a built core itself – callbacks via ctypes, MIDI through a FIFO as
`ADL_MIDI_DEV`, audio into a WAV. That makes bank loading, the MIDI parser, pitch, note-off and
levels testable on the host before anything goes to the device:

    make -C cores/adl
    scripts/adl_harness.py --demo demo.wav        # 6 bars, 120 bpm, lead/bass/pad/drums
    scripts/adl_harness.py --tone 69 a4.wav      # single note, measures the fundamental

Measured (DOSBox emulator, embedded bank 0, one chip): pitch accurate to 0.1 % across four octaves,
note-on to first sample 2.96 ms (OPL3 attack; MIDI is polled once per `retro_run`, so add 0–16.7 ms
of quantization), a four-voice demo at gain 6 peaking at -5.9 dBFS without clipping.

**Levels:** `adl_generate` comes out about 20 dB below full scale (single note at -33 dBFS; even the
loudest of libADLMIDI's 15 volume models only reaches -24 dBFS). The core therefore applies a fixed
output gain with saturation, default 6 (+15.6 dB), adjustable via `ADL_GAIN=1..64`.

## Checkpoints

Phase 0 -> SSH on both devices. Phase 2 -> aseqdump shows notes. Phase 4.1 -> real latency known
(above ~40 ms Track B only makes sense for sequencer use). Phase 4.3 -> first instrument in the
carousel. Phase 5 -> first core of our own, the rest is copying.
