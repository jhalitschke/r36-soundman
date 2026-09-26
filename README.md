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

    scripts/      host tools (usb-net-host, dtb-otg, inventory, diag, run, build, deploy, adl_harness)
    ssh/          example for ~/.ssh/config (r36a, r36b)
    docker/       arm64 build container
    es/systems/   ES system fragments, merged into the device file by es-merge.py
    ports/        launch scripts following the PortMaster pattern -> /roms/ports/<name>/
    tools/        device-side scripts for the ES Options menu -> /roms/tools/
    cores/        libretro cores (adl = OPL3 via libADLMIDI, opn = YM2612 via libOPNMIDI)
    tests/        hardware-free tests (ES merge, core API, core audio)
    device/<h>/   per device: inventory + copies of es_systems.cfg (gitignored)

## One-time setup on the host

    sudo apt install rsync docker.io                                 # Ubuntu
    docker run --privileged --rm tonistiigi/binfmt --install arm64    # arm64 emulation
    cat ssh/config.example >> ~/.ssh/config

The emulation line used to read `qemu-user-static binfmt-support`, which no longer installs: on
current Ubuntu `qemu-user-static` is a virtual package and the real ones are `qemu-user-binfmt` and
`qemu-user-binfmt-hwe`. The container registers the same `binfmt_misc` handler and keeps working.
Without it every arm64 container dies with `exec format error`.

If `docker build` fails with `mkdir ~/.docker/buildx/instances: permission denied`, that directory
belongs to root from some earlier `sudo docker` - `sudo chown -R "$USER:$USER" ~/.docker` fixes it
for good, and `DOCKER_CONFIG=$(mktemp -d)` works around it without touching anything.

macOS: Docker Desktop does arm64 without any of this. RNDIS needs HoRNDIS there; CDC-ECM works
natively.

## Phase 0 – SSH over the cable

ArkOS ships no USB Network Mode of its own, so the gadget comes from
[ctgl1987/arkos-usb-network-mode](https://github.com/ctgl1987/arkos-usb-network-mode): one script that
runs from RAM, loads `g_ether` with a fixed MAC, puts **10.44.44.1** on the handheld's `usb0` and
serves DHCP and SSH from there. Nothing is installed permanently, and its option 5 puts the port back.

Installed with a card reader, because without the cable there is no other way in. Handheld off, card
in the host; the ROMs partition is `EASYROMS` (exFAT, mounted `fmask=0022`, so the file is executable
where it lands) and the boot partition is `BOOT`:

    cp "USB Network Mode.sh" /run/media/$USER/EASYROMS/tools/
    scripts/dtb-otg.py /run/media/$USER/BOOT/*.dtb            # report
    scripts/dtb-otg.py --write /run/media/$USER/BOOT/rk3326-r36sPlus-linux.dtb \
                               /run/media/$USER/BOOT/gameconsole_linux.dtb

The second command is not optional on an R36S – see below. Patch the DTBs that `boot.ini` and
`boot01.ini` name, then it does not matter which one u-boot reads. `.orig` copies are left next to
them.

On the host, once:

    echo 'blacklist cdc_subset' | sudo tee /etc/modprobe.d/r36-no-cdc-subset.conf
    scripts/usb-net-host.sh -w 60

The blacklist is not optional: `cdc_subset` claims the device id `0525:a4a2` wholesale and can bind
the data interface before `rndis_host` claims it for the RNDIS handshake, leaving a link that carries
nothing. The script then creates a NetworkManager profile with a static 10.44.44.2, bound to the
gadget's MAC rather than to an interface name - the kernel names the interface after the USB bus
path, which changes with the port. Upstream's `setup-linux.sh` solves the naming with a udev rule and
needs root; this does not.

Then, in this order, because each step is forced by something further down:

1. Boot the handheld. `tools/r36-usbnet.service` brings the gadget up with ssh and a DHCP server.
2. **Then** plug the cable in - **into a hub**, never a port on the PC's own xHCI controller.
3. `ssh r36a`.

Both parts of step 2 are load-bearing. A root port does not enumerate this gadget at all, and the
cable has to go in *after* the gadget is loaded: with `dr_mode = "peripheral"` the controller sees
the VBUS session during boot, when nothing is bound yet, and never re-asserts its pull-up. Replugging
is also the only way to change anything about the gadget - see below.

The device side is `tools/r36-usbnet`, installed to `/usr/local/bin`. It loads `g_ether`, puts
10.44.44.1 on `usb0` and starts sshd and dnsmasq. Its unit needs `KillMode=process`: the script
starts dnsmasq and exits, and with the default the whole control group goes down with it, taking the
DHCP server along - which looks exactly like a dead link from the PC. The static address on the host
means that no longer matters, which is why it is static.

### The otg-port trap

On this card all six DTBs describe the dwc2 controller correctly and then take its PHY away:

    /usb@ff300000                           dr_mode  = "otg"       ok
    /usb@ff300000                           status   = "okay"      ok
    /usb@ff300000                           phys     = <0x8b>
    /syscon@ff2c0000/usb2-phy@100/otg-port  phandle  = <0x8b>
    /syscon@ff2c0000/usb2-phy@100/otg-port  status   = "disabled"  <-

`phys` points at exactly the port the device tree switches off, and the Rockchip PHY driver skips
disabled child nodes, so the OTG port is never registered and dwc2 is never told that a host is on
the cable. Every check that only looks at `dr_mode` passes, which is why the symptom is
indistinguishable from a charge-only cable or unwired data lines – and why upstream's troubleshooting
ends up suggesting `dr_mode = "peripheral"`.

`scripts/dtb-otg.py` sets that one property to `okay`. It keeps the property length (the kernel reads
`status` with `strcmp`, so `okay` plus NUL padding still reads as `okay`), which means no offset in
the DTB has to be recomputed: the file keeps its size and 8 bytes change. It writes `<dtb>.orig`
first, reads the result back and restores the backup if the check fails. `tests/test_dtb_otg.py`
builds a DTB and asserts all of that without a card in the reader.

Host mode on that port survives the change: with `dr_mode = "otg"` and a working PHY the ID pin
decides, so an OTG hub still comes up as host – which is what phase 1 needs.

### When the controller stays host

Enabling the PHY is not always enough. With `dr_mode = "otg"` the role comes from the ID pin, and on
boards where nothing pulls it low the controller stays host: a UDC exists, `g_ether` loads, `usb0`
gets its address – and the UDC never leaves `not attached`, because from its point of view no host
ever showed up. The tell is that the handheld *powers* what you plug into that port.

    scripts/dtb-otg.py --write --dr-mode peripheral /run/media/$USER/BOOT/<dtb>

That forces the gadget role. The price is host mode on that port: no OTG hub, so phase 1 has to move
to the other USB-C port or wait. Both DTBs on the card can be patched differently – then the `load
mmc 1:1 ${dtb_loadaddr} <file>` line in `boot.ini` is the switch between "device" and "host".

`dr_mode` grows from 4 to 11 bytes, so this one cannot be an in-place edit like the status patch: the
struct block is rebuilt and every offset in the header recomputed. Verified against the card's own
89 KB DTB – 2619 properties, structure and order unchanged, exactly the two intended values
different, `totalsize` matching the file.

What the phy driver also offers, and what it is worth: `otg_mode` under
`/sys/devices/platform/*syscon*/*usb2-phy*/`. It takes `host`, `peripheral` and `otg` at runtime, but
with `dr_mode = "peripheral"` already in the devicetree the driver answers `Same as current mode` and
does nothing – the devicetree has settled it at probe time. The sysfs knob is only interesting on a
card whose DTB has not been patched.

### Reading the signals in the right order

Three sources disagree on this hardware, and only two of them mean anything:

| source | on r36a | worth |
|---|---|---|
| `extcon` | `USB=0 USB_HOST=1 USB_VBUS_EN=1`, permanently | **none** |
| `/sys/class/udc/*/state` | `not attached` | the device's own verdict |
| the *host's* `dmesg` | `Cannot enable. Maybe the USB cable is bad?` | what actually happens on the wire |

The extcon flags keep claiming host role and VBUS output while the phy driver reports peripheral, and
the devicetree has neither a `vbus-supply` nor any regulator that could switch VBUS – one
`regulator-fixed` for `vcc3v8_sys`, always on, no GPIO. So the flags describe nothing the driver can
even do. Upstream says as much in its own README; it is worth believing the first time.

The host's kernel log is the source that was missing longest, because `kernel.dmesg_restrict` hides
it from an unprivileged shell. `sudo dmesg -W` on the PC while plugging in is the single most
informative thing available – it is the only place where the failure is described rather than
implied.

### The root port fails, the hub works

On r36a the gadget never enumerated on a port of the laptop's own xHCI controller - `Cannot enable.
Maybe the USB cable is bad?`, `attempt power cycle`, `unable to enumerate USB device`, over and over.
Plugged into a hub instead (any hub - a dock counts) it enumerated on the first try. xHCI root ports
are strict about the high-speed chirp handshake; a USB 2.0 hub runs that handshake itself and is far
more forgiving. This is the first thing to try, before doubting the board.

### cdc_subset steals the RNDIS data interface

Enumerated is not connected. g_ether offers two configurations, and with `use_eem=1` - which is what
this firmware loads - they are:

    config 1   02/0c/07   CDC EEM
    config 2   e0/01/03 + 0a/00/00   RNDIS: control + data

The host picks config 2. `cdc_subset` claims the device id `0525:a4a2` wholesale, gets probed first
and binds the *data* interface; `rndis_host` then cannot claim it, so the RNDIS INITIALIZE handshake
never happens. The link comes up and carries nothing: `NETDEV WATCHDOG: transmit queue 0 timed out`,
zero valid packets, and rx_errors climbing by about 170 a second.

The fix is to keep `cdc_subset` off it. With the module unloaded, `rndis_host` binds both interfaces
by itself and the host interface takes the gadget's `host_addr` - RNDIS transfers it, while EEM and
the CDC subset leave the host to invent a random MAC, which is why a profile matched on that MAC only
starts working here.

    modprobe -r cdc_subset      # then replug

### The host picks RNDIS on purpose

`g_ether use_eem=0` makes config 1 a CDC ECM, and a Linux host still takes config 2 and binds
`rndis_host`. That is not a race and not a bug: `usb_choose_configuration()` deliberately prefers an
RNDIS configuration whenever `CONFIG_USB_NET_RNDIS_HOST` is available. As long as `g_ether` offers
RNDIS at all, RNDIS is what gets used, and `cdc_ether` never gets a look in.

So `ecm` here buys one thing only - the configuration the host ignores is a standard ECM rather than
an EEM. The link itself runs on RNDIS either way, cleanly: `rx_errors` 0, 0.5 ms round trip. Getting
ECM actually bound would mean a gadget that offers no RNDIS config at all, which means `g_ncm` or
building one by hand through configfs. Not worth it while this works.

### Reloading the gadget is not a reconnect

Swapping the gadget module on the device does not make the host re-enumerate. A `try` run walked
ncm -> ecm -> eem, reloading three times over four minutes, and the host's view never moved off
`0525:a4a2 cfg=2 rndis_host` - the device it first saw. rx_errors climbed steadily to 48000 the whole
time, because the PC kept talking to a gadget that had been unloaded underneath it. dwc2 on this BSP
kernel does not drop the D+ pull-up when the UDC is unbound, so the disconnect the host needs never
happens.

Consequences, and they are not small:

- **Only pulling the cable counts.** Every mode change has to be followed by a physical replug.
- **Walking the modes automatically is pointless here** - the host sees none of them.
- The `I/O error` from a `SET_CONFIGURATION` or a driver bind is the same thing seen from the other
  side: a control transfer to a gadget that is no longer there.

So pick one mode, set it at boot, and plug the cable in afterwards. One deliberate handle, forced by
the hardware, instead of a retry loop that cannot work.

### What an external hard disk does not prove

A USB-C cable that works for an external disk says nothing about this. The disk runs at SuperSpeed
over the TX/RX pairs; the gadget is High-Speed and uses **only D+/D-**. A cable can have perfect
SuperSpeed pairs and a dead USB 2.0 pair, and nothing you normally plug in would notice. Test a
suspect cable with something that is USB 2.0 – a phone in file-transfer mode. A USB-C-to-A cable also
carries a 56 kΩ pull-up in its C plug, which tells the handheld that a host is on the other end, so
it answers the cable question and the role question at once.

### Debugging without SSH

Until the cable works there is no shell on the device, so `tools/USB Diag.sh` goes next to the other
one in `EASYROMS/tools/` and writes to `/roms/usbnet-diag.txt`, which is readable from a card reader.
It reports what the *booted* devicetree says (so a patch that never took effect cannot be mistaken for
a hardware limit), every UDC and its state, the dwc2 and usb2phy sysfs trees, the loaded gadget
modules, `usb0`, DHCP leases, extcon and the relevant `dmesg` lines.

### Internet over the same cable

PortMaster, `apt` and NTP all need the handheld to reach the network, and the cable can carry that
too - the direction just has to be agreed on both ends:

    scripts/usb-net-host.sh --share     # this PC serves and NATs its wifi
    ssh r36a 'r36-usbnet internet'      # the handheld asks for an address instead of handing them out

Neither end reloads the gadget, so this is addressing only and needs no replug - which is what makes
it safe to run over the link it is changing. If nothing answers within the timeout the handheld goes
back to serving on 10.44.44.1 by itself, so a failed attempt costs a minute rather than a card.

Measured on r36a: an address from the PC's dnsmasq, 16 ms to 8.8.8.8, `curl https://github.com`
returning 200. Docker's `FORWARD` policy, which upstream's `setup-linux.sh` works around with a
dispatcher script, did not get in the way here.

Back to the other direction with `scripts/usb-net-host.sh` and `r36-usbnet files`. One caveat worth
knowing: in internet mode the handheld's address comes from DHCP, so it is no longer the 10.44.44.1
that `ssh/config.example` calls `r36a` - the host script prints where it actually is.

## Phase 1 – Host mode + USB Ethernet on the OTG hub

The drivers are there: the card carries `r8152.ko`, `cdc_ether.ko`, `rndis_host.ko`, `asix.ko` and
`ax88179_178a.ko` under `/lib/modules/4.4.189/kernel/drivers/net/usb/`. So: gadget off (script option
5), attach the OTG hub with an RTL8152/8153 adapter, set host Ethernet to "Shared to other computers"
and point `HostName` in `~/.ssh/config` at the DHCP address. From then on Ethernet, MIDI and a
keyboard hang off the hub at the same time.

Fallback: deploy over the gadget, run tests with `nohup ... > log.txt 2>&1 &`, unload the gadget
(option 5), test MIDI, load it again, read the log.

## Phase 2 – Diagnostics

    scripts/diag.sh r36a          # aplay/amidi/aseqdump -l
    scripts/diag.sh r36a 20:0     # dump 5 s of events from that seq port

If alsa-utils is missing: arm64 `.deb` matching `lsb_release` from ports.ubuntu.com, `scp`,
`sudo dpkg -i`. No sound: `amixer cset name='Playback Path' SPK` (or `HP`).

Check: notes arrive in `aseqdump`. Only then continue.

### Phase 2 on this board: one port, and it is contested

Measured on r36a, all of it with `tools/Boot Role.sh` and `tools/MIDI Diag.sh`:

- The host role works. With `gameconsole_linux.dtb` (dr_mode="otg") dwc2 runs as a host and hands out
  addresses.
- USB MIDI needs nothing installed: `snd-usb-audio` and `snd-usbmidi-lib` are **built into** the
  kernel (they are in `modules.builtin`, which is why `/lib/modules/*/kernel/sound` is empty), and so
  is the ALSA sequencer.
- **The internal wifi is on the same dwc2 port** and is dropped the moment anything is plugged in
  (`usb 1-1: USB disconnect` followed by `R8188EU: indicate disassoc`). One controller, one port,
  and the network, the cable and any peripheral all want it.

What has not worked yet, and why each attempt proves less than it looks:

| tried | result | what it actually says |
|---|---|---|
| KeyStep Pro behind a Dell WD19 | `can't read configurations, error -71` | a Thunderbolt dock expects PD negotiation this port cannot do |
| DDJ-FLX4 directly, externally powered | device froze, only a reset helped | not power. Suspect the dwc2 host path with isochronous transfers - the FLX4 is an audio device, not MIDI-only |

The test still missing is the cheap one: a **MIDI-only, self-powered device straight on the port** -
a KeyStep Pro on its 12 V supply through a USB-C-to-B cable. If that enumerates, phase 2 is done and
the FLX4 was a special case. If it does not, the dwc2 host driver of this 4.4 BSP is the problem, and
MIDI has to reach the device some other way than USB.

The `128 invalid for host_nperio_tx_fifo_size` line in the boot log is **not** a lead: dwc2 clamps
the value to what the hardware reports and carries on. `/sys/module/dwc2/parameters` is empty, so
there is nothing to tune there either.

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

**4.1 synth (FluidSynth, end-to-end test)** – `fluidsynth` 1.1.11 is already on the card
(`/bin/fluidsynth`), so this is only a `.sf2` in `/roms/synth/` plus a deploy. The soundfont is
content, like a ROM: none ships here.

The port already asks for the card directly (`audio.alsa.device=hw:0`), which is the same lesson the
cores had to be taught, and `-z`/`-c` default to 256x2 = 512 frames, 10.7 ms. It accepts everything
down to `-z 16` without complaint - but with no soundfont and no MIDI it synthesizes nothing, so that
measures the driver setup and not the load. The real floor needs a keyboard.

What the runs did settle: **a normal user on this device cannot have realtime priority at all.**
`RLIMIT_RTPRIO` is 0, which is why fluidsynth says `Failed to set thread to high priority` whatever
the buffer size. Lowering niceness *does* work - `nice -n -19` returns -19 for `ark` - so the port
script now does what ArkOS's own 123 commands do and asks for -19. That is the whole of what is
available here without changing the system's scheduling limits. Select+Start quits. Latency: turn `PERIOD`/`COUNT` in the
script (`-z`/`-c`) down until it crackles – that is the device's floor.

**4.2 chiptune (GME core)** – `scripts/build.sh gme`. `cores/gme/Makefile` clones
libretro/libretro-gme at a pinned revision and runs its own Makefile with `platform=unix`; the `.info`
comes from upstream. Unlike `adl` and `opn` this core is not ours and is **GPL-3.0** where ours are
MIT, which is the reason it is built rather than vendored - the `.so` is gitignored, so nothing here
redistributes a binary, and `GME_REV` records exactly which source it came from.

Verified on r36a: it refuses to start without content, and with content it comes up at 320x240 / 60
fps and takes the low-latency device like ours do. Note it runs at **44100 Hz**, not the 48000 our own
cores use - it is upstream's core, not one written to our conventions, so `tests/core_smoke.py` is
not pointed at it. Content goes to `/roms/chiptune/`; a 68-byte VGM of silence, written by hand, is
enough to prove the path without dragging anyone's game music into the repo.

**4.3 picoloop** – built, deployed and running on r36a: it comes up with its wavetables, mixers and
SDL GUI, stays there across 14 threads and exits cleanly. It does **not** open the sound card while
it sits on its config page, which is the first screen and needs **A** to leave - so the audio path is
the one thing here that a button press has to confirm. `scripts/build.sh picoloop`. The makefile is settled:
`Makefile.PatternPlayer_raspi1_RtAudio_sdl20`, the Raspberry Pi 1 target. It is SDL2, uses
fixed-point maths (`-DFIXED`) and compiles only Picosynth, Picodrum, OPL2 and PBSynth, so
Twytch/Open303/Cursynth need no switching off - they are makefile defines, not `Master.h`. The
build script patches RtAudio from PulseAudio to ALSA, because ArkOS has neither PulseAudio nor
libpulse. The binary is called `PatternPlayer_raspi1_sdl20` and is copied to `picoloop`; `font.ttf`
and `font.bmp` have to sit next to it. The first screen is the config page (palette, bank, audio
output); **A** (Left-Ctrl) leaves it.

**4.4 lgpt** – `harbourmaster install littlegptracker.zip` over the shared connection (see phase 0),
then one empty `song.lgpt` per project folder under `/roms/lgpt/`.

The open `LGPT_BIN` question is answered, and the old guess was wrong twice over. The port installs
its launcher as `/roms/ports/LittleGPTracker.sh` and its files in `/roms/ports/littlegptracker/`
(lower case), with the binary at `littlegptracker/lgpt`. And that launcher **takes no arguments** -
it cds into the port and runs `./lgpt` bare - so it cannot be handed a project. What it sets up has
to be repeated instead, which is what `ports/lgpt/lgpt.sh` now does: library and XDG paths, the
screen multiplier, gptokeyb with the port's own `lgpt.gptk`, then the binary with the project folder.

Verified on r36a: LGPT comes up, `Installing SDL audio` with a 512-frame buffer, `Installing DUMMY
MIDI` (nothing attached), `Using driver KMSDRM. Screen (720,720)`, and stays running. Whether it
opens the right project still wants eyes on the screen. Worth knowing: upstream's own launcher fails
two arithmetic lines on this device because `DISPLAY_WIDTH` is unset in its environment - ours guards
against that.

**4.5 theme** – the logos exist: `es/theme/logos/<system>.svg` and `.png` for synth, chiptune,
adlib, opn, lgpt and picoloop, generated by `python3 es/theme/make-logos.py`. They are drawn from pixel
grids, so both formats come out of one description and cannot drift apart, and there is no `<text>`
element - EmulationStation renders SVG through nanosvg, which does not draw text. Each logo is an
icon plus a pixel wordmark with a hard shadow, so it stays readable on a light theme background as
well. A new system is four lines in `SYSTEMS` plus a 16x16 icon.

r36a runs **gameconsole-sagabox**, and it takes logos as `_art/logos/${system.theme}.png` - one flat
directory, 179 of them, named after the system's `<theme>`. So the fragments now set `<theme>` to
their own name and `deploy.sh` copies the PNGs into whichever ThemeSet `es_settings.cfg` has switched
on. A logo the theme already ships is never overwritten, and switching themes means deploying again.

Two things that theme taught us, both visible in `es_log.txt`: a system needs **no folder of its own**
in the theme - 11 of ArkOS's own systems have none and ES simply carries on - and a missing logo is a
warning, not an error. So the footprint is six PNG files and nothing else.

## Phase 5 – Track B (libretro cores)

    scripts/build.sh adl          # cores/adl/adl_libretro.so (arm64) + the glibc check
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
bank**, so `opn` refuses to start without content. Confirmed on r36a, all three cases:

    no content    [ERROR] [Content]: Libretro core requires content, but nothing was provided.
    empty file    [libretro ERROR] [opn] bank: Custom bank: Unexpected ending!
    real bank     [libretro INFO] [opn] bank /roms/opn/xg.wopn / Gain 4.00

The middle one is the one to keep an eye on when the next core is copied from this one: `adl` treats
an empty file as "use the embedded bank", `opn` has nothing to fall back to and says so. A core that
quietly played silence instead would be the worst of both. Put a `.wopn` in `/roms/opn/` - libOPNMIDI ships
twelve in `fm_banks/` (check their individual licences before shipping one) or build your own with
the WOPN editor. The next engine is the same copy again with mt32emu, whose ROMs go into RetroArch's
`system/`.

### What the first run on the device said

    [libretro INFO] [adl] /roms/adlib/embedded.wopl is empty, embedded bank 0
    [libretro INFO] [adl] Gain 6.00
    [libretro INFO] [adl] MIDI (no rawmidi device) -> FAILED, retrying once a second
    [INFO] [Core]: Geometry: 320x240, Aspect: 1.333, FPS: 60.00, Sample rate: 48000.00 Hz.
    [INFO] [ALSA]: Period: 4 periods per buffer (1024 frames, 8192 bytes)
    [INFO] [ALSA]: Buffer size: 4096 frames (32768 bytes)
    [INFO] Threaded video stats: Frames pushed: 1422, Frames dropped: 14.

Everything the conventions promise holds on the hardware: the empty marker reaches the embedded bank,
the AV info matches, ALSA accepts the output and the RK3326 keeps 60 fps. The MIDI open failing is
correct - nothing is attached - and it fails by retrying rather than by dying, which is what lets the
core be started before the keyboard is plugged in.

### The latency floor is in ArkOS's asound.conf, not in the hardware

The first run came out at 4096 frames, **85 ms** at 48 kHz. Turning `audio_latency` down stops
helping below 32:

    audio_latency   128    64     32     16     8
    buffer         4096  3072   2048   2048  2048      frames
                   85.3  64.0   42.7   42.7  42.7      ms

That looks exactly like a hardware limit and is not one. ALSA's `default` on ArkOS is a dmix mixer
with the period written into the config:

    pcm.!default -> plug -> dmixer
    pcm.dmixer   -> dmix, slave hw:0,0, period_size 1024, buffer_size 4096, rate 44100

Nothing a client asks for gets under those 1024 frames. Pointing RetroArch at the card instead does:

    audio_device = "plughw:0,0"
    audio_latency = "12"

    device        latency  buffer  period    ms
    default            16    2048    1024  42.7
    plughw:0,0         16     768     192  16.0
    plughw:0,0          8     384      96   8.0
    plughw:0,0          4     192      48   4.0

`hw:0,0` works too and is handed S16_LE instead of FLOAT_LE, since the card has no float format and
`plug` is what converts.

Where it stops working, from 45-second runs counting `snd_pcm_recover` in the log:

    latency    16    12    10     8  |    5     4     2
    underruns   1     0     1     1  |    2     8   113
                    (one sample each)|  (14 s runs)

Below 8 ms it comes apart, monotonically and unmistakably. Between 8 and 16 the single underruns move
around and do not track the buffer size - one sample each is not enough to rank them, and reading an
order into 0-versus-1 would be inventing a result. **16 ms** is the choice on margin rather than on
measurement: more headroom against scheduling jitter, still a fifth of what dmix imposes and well
inside the 40 ms the checkpoint cares about.

It is applied to our systems and to nothing else. `es/retroarch-lowlatency.cfg` goes to the device
as `~/.config/retroarch/r36-lowlatency.cfg`, and `{{APPEND}}` in the RetroArch fragments becomes the
`--appendconfig` that names it - so three of the device's 129 systems carry it and ArkOS's emulators
keep the mixer they were written for. The device's own `retroarch.cfg` is not touched at all; its
checksum is the same before and after a deploy. Running the command ES will run gives:

    [ALSA]: Using FLOAT_LE sample format for PLAYBACK device "plughw:0,0"
    [ALSA]: Period: 4 periods per buffer (192 frames, 1536 bytes)
    [ALSA]: Buffer size: 768 frames (6144 bytes)

What this costs: dmix exists so several programs can play at once, and going direct takes the card
exclusively. That is no loss here - `run.sh` and the ES commands stop EmulationStation anyway, and a
synth wants the card to itself - but nothing else can make a sound while a core is running.

And what it does **not** prove: every one of these runs was silent, because without MIDI the core
emits silence. Silence exercises the timing, so an underrun count means something; it says nothing
about whether the result sounds clean. That needs a keyboard on the port, which is phase 2.

### The container's Ubuntu is not the question

`scripts/build.sh` ends with `scripts/glibc-check.py`, which reads `.gnu.version_r` out of everything
it just built and refuses anything the device cannot load. That is the check worth having: the
release the container is based on says nothing, the symbol versions the linker bound say everything.

Measured on `adl`, cross-built in a 20.04 container for r36a's 19.10:

    libc.so.6       GLIBC_2.17 GLIBC_2.27
    libm.so.6       GLIBC_2.17 GLIBC_2.29        <- the highest, device has 2.30
    libstdc++.so.6  CXXABI_1.3.9 GLIBCXX_3.4.21  <- device has 1.3.12 and 3.4.28

So the two-release gap never mattered. Most symbols sit at `GLIBC_2.17`, the aarch64 base version,
whatever the build image is. The C++ runtime is checked as well, since the cores link libstdc++ for
their upstream library - a core that loads and then dies on a missing `GLIBCXX_` is the same failure
wearing a different name.

A cross-built .so lands where a host-side `make` would put one, and `dlopen` reports a foreign
architecture as "No such file or directory". The core tests therefore read the ELF's `e_machine` and
skip, rather than erroring about a file that is plainly there.

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
