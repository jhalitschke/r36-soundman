# r36-soundman

Synths, Tracker und MIDI auf dem R36S (ArkOS) – als EmulationStation-Systeme und als libretro-Cores.
Alles wird vom Host (Ubuntu, alternativ macOS) per SSH gebaut, deployt und getestet.

## Layout

    scripts/      Host-Werkzeuge (usb-net-host, inventory, diag, run, build, deploy)
    ssh/          Beispiel für ~/.ssh/config (r36a, r36b)
    docker/       arm64-Build-Container
    es/systems/   ES-System-Fragmente, werden per es-merge.py in die Gerätedatei gemergt
    ports/        Startscripts nach PortMaster-Muster -> /roms/ports/<name>/
    cores/        libretro-Cores (adl = OPL3 via libADLMIDI)
    device/<h>/   pro Gerät: Inventar + Kopien von es_systems.cfg (gitignored)

## Einmalig auf dem Host

    sudo apt install rsync docker.io qemu-user-static binfmt-support   # Ubuntu
    cat ssh/config.example >> ~/.ssh/config

macOS: Docker Desktop kann arm64 ohne qemu-Paket. RNDIS braucht dort HoRNDIS; CDC-ECM geht nativ.

## Phase 0 – Kabel-SSH (RNDIS)

1. Handheld: Options -> USB Network Mode einschalten, USB-C-Kabel an den Host.
2. `scripts/usb-net-host.sh` (legt 192.168.7.2/24 auf usb0/enx*).
3. `ssh ark@192.168.7.1` (pw `ark`), dann `ssh-copy-id r36a`.
4. Taucht kein Interface auf: https://github.com/ctgl1987/arkos-usb-network-mode, Option 1 prüft,
   ob das Board Device-Mode überhaupt kann. Ein NOT SUPPORTED-Gerät wird Referenzgerät.

Check: `scripts/inventory.sh r36a` läuft durch und schreibt `device/r36a/`.

## Phase 1 – Host-Mode + USB-Ethernet am OTG-Hub

In `device/r36a/inventory.txt` nachsehen: `r8152`/`cdc_ether` als `=y` oder `.ko` vorhanden?
Dann RNDIS aus, OTG-Hub mit RTL8152/8153-Adapter dran, Host-Ethernet auf "Shared to other computers",
`HostName` in `~/.ssh/config` auf die DHCP-IP setzen. Ab jetzt hängen Ethernet, MIDI und Tastatur
gleichzeitig am Hub.

Fallback ohne Treiber: RNDIS zum Deployen, Tests mit `nohup ... > log.txt 2>&1 &`, Gadget
entladen (Script Option 5), MIDI testen, Gadget wieder laden, Log lesen.

## Phase 2 – Diagnose

    scripts/diag.sh r36a          # aplay/amidi/aseqdump -l
    scripts/diag.sh r36a 20:0     # 5 s Events vom Seq-Port dumpen

Fehlt alsa-utils: arm64-.deb passend zu `lsb_release` von ports.ubuntu.com, `scp`, `sudo dpkg -i`.
Kein Ton: `amixer cset name='Playback Path' SPK` (bzw. `HP`).

Check: Noten kommen in `aseqdump` an. Erst dann weiter.

## Phase 3 – Deploy-Loop

    scripts/deploy.sh r36a        # ports/ -> /roms/ports, Cores -> libretro_directory, ES-Systeme mergen, ES neu starten
    scripts/run.sh r36a '<cmd>'   # ES stoppen, Kommando im Vordergrund, ES starten

Das Original der es_systems.cfg liegt danach als `/etc/emulationstation/es_systems.cfg.orig` auf dem Gerät.
`{{RA}}` und `{{CORES}}` in den Fragmenten werden aus dem ersten RetroArch-Command der Gerätedatei abgeleitet.

## Phase 4 – Track A (ArkOS/ES)

**4.1 synth (FluidSynth, Kettentest)** – `fluidsynth` + `libfluidsynth` als arm64-.deb installieren,
`.sf2` nach `/roms/synth/`, deployen. Select+Start beendet. Latenz: `PERIOD`/`COUNT` im Script
(`-z`/`-c`) so weit runter, bis es knackt – das ist die Untergrenze des Geräts.

**4.2 chiptune (GME-Core, nur Config)** – `gme_libretro.so` (arm64: libretro-Buildbot oder Build im
Container aus libretro/libretro-gme) nach `cores/gme/` legen, `.info` daneben, deployen.
Content nach `/roms/chiptune/`.

**4.3 picoloop** – `scripts/build.sh picoloop`. Vorher in `ports/picoloop/build.sh` das SDL2-Linux-Makefile
eintragen (Script listet die vorhandenen) und in `Master.h` Twytch/Open303/Cursynth abschalten.
Erster Start fragt das Audio-Device ab: `default` oder `hw:0`.

**4.4 lgpt** – Port über PortMaster installieren, `LGPT_BIN` in `ports/lgpt/lgpt.sh` anpassen.
Pro Projektordner unter `/roms/lgpt/` eine leere `song.lgpt`.

**4.5 Theme** – bis eigene Logos da sind, nutzen alle Systeme `theme="ports"`.

## Phase 5 – Track B (libretro-Core)

    scripts/build.sh adl          # cores/adl/adl_libretro.so (arm64)
    scripts/deploy.sh r36a
    scripts/run.sh r36a 'retroarch -L $(grep ^libretro_directory ~/.config/retroarch/retroarch.cfg | cut -d\" -f2)/adl_libretro.so --verbose'

Der Core liest `/dev/snd/midiC*D*` selbst (Override `ADL_MIDI_DEV`), braucht also kein MIDI-fähiges
RetroArch. Anzeige: grün/rot = MIDI-Device offen, 16 Balken = Kanalaktivität. L/R = Program, A = Panic.
Content optional (`.wopl`-Bank nach `/roms/adlib/`), ohne Content eingebettete Bank 0.
Emulator ist DOSBox-OPL (leichter als Nuked); `adl_switchEmulator` in `adl_libretro.c`.

Weitere Engines = Kopie von `cores/adl/` mit anderer Lib: libOPNMIDI (`opn2_*`, `.wopn`),
mt32emu (ROMs nach RetroArch `system/`).

## Checkpoints

Phase 0 -> SSH auf beiden Geräten. Phase 2 -> aseqdump zeigt Noten. Phase 4.1 -> reale Latenz bekannt
(über ~40 ms: Track B nur für Sequencer-Betrieb sinnvoll). Phase 4.3 -> erstes Instrument im Karussell.
Phase 5 -> erster eigener Core, der Rest ist Kopieren.
