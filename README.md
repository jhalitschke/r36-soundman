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
    cores/        libretro cores (adl = OPL3 via libADLMIDI, opn = YM2612 via libOPNMIDI)
    tests/        hardware-free tests (ES merge, core API, core audio)
    device/<h>/   per device: inventory + copies of es_systems.cfg (gitignored)

## One-time setup on the host

    sudo apt install rsync docker.io qemu-user-static binfmt-support   # Ubuntu
    cat ssh/config.example >> ~/.ssh/config

macOS: Docker Desktop does arm64 without the qemu package. RNDIS needs HoRNDIS there; CDC-ECM works
natively.

## Phase 0 – SSH over the cable (USB gadget)

ArkOS has **no USB network entry of its own** - the menu item comes from a script that has to be on
the card first, and that is the one step the cable cannot do for you. Nothing is installed
permanently: the gadget runs from RAM and option 5 puts the port back.

1. Handheld off, card into a reader on the host. Of its three partitions the big one is the ROMs
   partition (`EASYROMS`). Copy `USB Network Mode.sh` from
   https://github.com/ctgl1987/arkos-usb-network-mode into its `tools/` folder - exFAT mounted with
   `fmask=0000`, so there is no `chmod` to do. Card back in, boot. `/opt/system` is on the ext4 root
   and is not the way in here.
2. **Options -> USB Network Mode -> option 1** first. It only reads, and ends in `SUPPORTED`,
   `SHOULD WORK, BUT...` or `NOT SUPPORTED`. A NOT SUPPORTED board becomes the reference device
   (`r36b`): its USB-C data lines never reach the SoC in device mode and no firmware fixes that.
3. Option 2 (universal). The handheld now runs `g_ether` plus its own dnsmasq and sits on
   **10.44.44.1** - the device hands out the addresses, so the host only takes DHCP.
4. Host: `scripts/usb-net-host.sh`. It finds the gadget interface by driver
   (`rndis_host`/`cdc_ether`/`cdc_ncm`) on the USB bus, takes DHCP from the handheld and pings it.
   It refuses any interface that is not a USB gadget - matching interface *names* is what used to
   put the handheld's address on the host's own LAN port, because `ip -o link` prints systemd's
   `altname enx<mac>` on the same line as the onboard NIC.
5. `ssh ark@10.44.44.1` (password `ark`), then `ssh-copy-id r36a`.

Use the **OTG** port and a **data** cable. A charge-only cable is by far the most common cause of
"nothing happens", and looks exactly like an unsupported board until option 1 says otherwise.

Once it works, upstream's `sudo ./setup-linux.sh` is worth running: it pins the gadget to the name
`arkos0` by udev rule (the kernel otherwise names it after the USB bus path, which changes with the
port) and stops NetworkManager inventing a fresh "Wired connection N" on every reconnect.

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

`deploy.sh` patches the es_systems.cfg ES actually reads - the user file in `~/.emulationstation/`
wins over `/etc/` - and leaves the original next to it as `.orig`. `{{RA}}` and `{{TAIL}}` in the
fragments come from the device file's own RetroArch command (a 64-bit one is preferred; ArkOS
usually ships retroarch and retroarch32 with separate core directories), and `{{CORES}}` is the
`libretro_directory` deploy.sh just copied the core into, not a second guess. The rom directories
come from the fragments' `<path>`, so a new system cannot be forgotten.

## Phase 4 – Track A (ArkOS/ES)

**4.1 synth (FluidSynth, end-to-end test)** – install `fluidsynth` + `libfluidsynth` as arm64 `.deb`,
put a `.sf2` in `/roms/synth/`, deploy. Select+Start quits. Latency: turn `PERIOD`/`COUNT` in the
script (`-z`/`-c`) down until it crackles – that is the device's floor.

**4.2 chiptune (GME core, config only)** – put `gme_libretro.so` (arm64: libretro buildbot or build
libretro/libretro-gme in the container) into `cores/gme/` with its `.info` next to it, deploy.
Content goes to `/roms/chiptune/`.

**4.3 picoloop** – `scripts/build.sh picoloop`. The makefile is settled:
`Makefile.PatternPlayer_raspi1_RtAudio_sdl20`, the Raspberry Pi 1 target. It is SDL2, uses
fixed-point maths (`-DFIXED`) and compiles only Picosynth, Picodrum, OPL2 and PBSynth, so
Twytch/Open303/Cursynth need no switching off - they are makefile defines, not `Master.h`. The
build script patches RtAudio from PulseAudio to ALSA, because ArkOS has neither PulseAudio nor
libpulse. The binary is called `PatternPlayer_raspi1_sdl20` and is copied to `picoloop`; `font.ttf`
and `font.bmp` have to sit next to it. The first screen is the config page (palette, bank, audio
output); **A** (Left-Ctrl) leaves it.

**4.4 lgpt** – install the port through PortMaster, adjust `LGPT_BIN` in `ports/lgpt/lgpt.sh`. One
empty `song.lgpt` per project folder under `/roms/lgpt/`.

**4.5 theme** – the logos exist: `es/theme/logos/<system>.svg` and `.png` for synth, chiptune,
adlib, opn, lgpt and picoloop, generated by `python3 es/theme/make-logos.py`. They are drawn from pixel
grids, so both formats come out of one description and cannot drift apart, and there is no `<text>`
element - EmulationStation renders SVG through nanosvg, which does not draw text. Each logo is an
icon plus a pixel wordmark with a hard shadow, so it stays readable on a light theme background as
well. A new system is four lines in `SYSTEMS` plus a 16x16 icon.

Where they go on the device depends on the theme that is actually installed, which the inventory
will show - most ES themes take a per-system `art/logo.svg`. Until that is known the systems keep
`theme="ports"`, and `deploy.sh` does not touch the theme.

## Phase 5 – Track B (libretro cores)

    scripts/build.sh adl          # cores/adl/adl_libretro.so (arm64)
    scripts/build.sh opn          # cores/opn/opn_libretro.so (arm64)
    scripts/deploy.sh r36a
    scripts/run.sh r36a 'retroarch -L $(grep ^libretro_directory ~/.config/retroarch/retroarch.cfg | cut -d\" -f2)/adl_libretro.so --verbose'

The core reads `/dev/snd/midiC*D*` itself (override `ADL_MIDI_DEV`), so it does not need a
MIDI-capable RetroArch. Display: green/red = MIDI device open, 16 bars = channel activity.
L/R = program, A = panic. Content is optional: a `.wopl` bank in `/roms/adlib/`, or the empty
`embedded.wopl` marker deploy.sh puts there, which selects the embedded bank 0 - ES can only launch
a system through a file, so without the marker the content-free mode is unreachable from the
carousel. A real but broken bank still fails loudly. The emulator is DOSBox OPL (lighter than Nuked); see `adl_switchEmulator` in
`adl_libretro.c`.

`cores/opn` is that same core with libOPNMIDI: YM2612/OPN2 instead of OPL3, MAME emulator instead of
DOSBox, gain 4 instead of 6. One difference matters on the device: **libOPNMIDI has no embedded
bank**, so `opn` refuses to start without content. Put a `.wopn` in `/roms/opn/` - libOPNMIDI ships
twelve in `fm_banks/` (check their individual licences before shipping one) or build your own with
the WOPN editor. The next engine is the same copy again with mt32emu, whose ROMs go into RetroArch's
`system/`.

## Tests & CI

Verifiable without the device, the same steps as in `.github/workflows/ci.yml`:

    for f in scripts/*.sh ports/*/*.sh; do bash -n "$f"; done
    shellcheck --severity=warning scripts/*.sh ports/*/*.sh
    make -C cores/adl && make -C cores/opn         # x86 compile check (not for the device)
    python3 tests/core_smoke.py cores/adl/adl_libretro.so
    python3 -m unittest discover -s tests          # es-merge, fragments, logos, core audio

`core_smoke.py` loads a `.so` via ctypes and checks the libretro API, the mandatory symbols,
48 kHz / 60 fps / 320x240, and whether the `.info` matches what the core reports. The audio tests
run against **every** built core - a new core is a copy, which is exactly where a MIDI-parser or
gain bug would go unnoticed - and skip themselves when nothing is built. The arm64 build (`scripts/build.sh adl`) only
runs in CI via *Run workflow* – qemu is too slow for every push. Every CI run uploads
`adl-demo.wav` plus screenshots as an artifact: a change to the core is audible and visible, not
just green.

## Harness: hearing the core without RetroArch

`scripts/adl_harness.py` drives a built core itself – callbacks via ctypes, MIDI through a FIFO as
`ADL_MIDI_DEV`, audio into a WAV. That makes bank loading, the MIDI parser, pitch, note-off and
levels testable on the host before anything goes to the device:

    make -C cores/adl
    scripts/adl_harness.py --demo demo.wav        # 6 bars, 120 bpm, lead/bass/pad/drums
    scripts/adl_harness.py --tone 69 a4.wav       # single note, measures the fundamental
    scripts/adl_harness.py --demo --shots shot    # the core's 320x240 screen as PNGs
    scripts/adl_harness.py --so cores/opn/opn_libretro.so \
      --bank cores/opn/libOPNMIDI/fm_banks/xg.wopn --demo opn.wav

It works for any core that follows the conventions: the environment variables are per core
(`ADL_MIDI_DEV`, `OPN_MIDI_DEV`, ...), and the prefix is taken from the name the core reports.

`--shots` captures the framebuffer the core hands to `video_cb` - the same pixels RetroArch would
put on the display - and writes them as PNGs (nearest-neighbour scaled, `--scale`, no dependencies).
That is what the screen shows: a green square when the rawmidi device is open and a red one when it
is not, the program as a white bar next to it, and 16 channel bars along the bottom that are
triggered by note-on and decay over about 0.7 s (channel 10 in orange for drums). The tests check
those pixels, so the display cannot silently break.

Measured (DOSBox emulator, embedded bank 0, one chip): pitch accurate to 0.1 % across four octaves,
note-on to first sample 2.96 ms (OPL3 attack; MIDI is polled once per `retro_run`, so add 0–16.7 ms
of quantization), a four-voice demo at gain 6 peaking at -5.9 dBFS without clipping.

**Levels:** `adl_generate` comes out about 20 dB below full scale (single note at -33 dBFS; even the
loudest of libADLMIDI's 15 volume models only reaches -24 dBFS). The core therefore applies a fixed
output gain with saturation, adjustable via `ADL_GAIN=1..64` / `OPN_GAIN=1..64`. The defaults put a
four-voice demo just under -6 dBFS: 6 for `adl`, 4 for `opn`, which starts out louder (-24.9 dBFS
for a single note).

## Checkpoints

Phase 0 -> SSH on both devices. Phase 2 -> aseqdump shows notes. Phase 4.1 -> real latency known
(above ~40 ms Track B only makes sense for sequencer use). Phase 4.3 -> first instrument in the
carousel. Phase 5 -> first core of our own, the rest is copying.
