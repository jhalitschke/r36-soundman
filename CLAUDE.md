# CLAUDE.md – r36-soundman

Synths, Tracker und MIDI auf dem R36S-Retro-Handheld (RK3326, ArkOS). Ziel: Instrumente stehen in
EmulationStation gleichwertig neben C64/Amiga – als ES-Systeme (Track A) und als libretro-Cores (Track B).
Entwicklung läuft komplett vom Host (Ubuntu, alternativ macOS) per SSH; auf dem Gerätedisplay wird nur verifiziert.

## Harte Rahmenbedingungen

- **CPU-Limit ist gesetzt.** RK3326 = 4× Cortex-A35 @ ~1,3 GHz. Chip-/FM-Emulation ja, subtraktive VA knapp,
  DSP-Emulation (gearmulator o.ä.) nein. Keine Engine vorschlagen, die auf einem Raspberry Pi Zero nicht liefe.
- **YAGNI, ponytail.dev-Leiter:** nötig? schon vorhanden? Stdlib? Plattform-Feature (PortMaster, gptokeyb, ALSA,
  libretro)? Erst dann eigener Code. Keine Frameworks, keine Abstraktionsschichten "für später".
  Ein neuer Core ist eine Kopie von `cores/adl/` mit anderer Lib, keine gemeinsame Engine-Abstraktion.
- **Alles über USB-C-Kabel.** WLAN-Dongles haben nicht funktioniert, internes WLAN ist unzuverlässig.
  SSH via RNDIS (Bootstrap) oder USB-Ethernet am OTG-Hub (Ziel). Nichts vorschlagen, das WLAN voraussetzt.
- **Nur ArkOS.** Rocknix/andere CFWs kommen nicht vor. Pfade sind ArkOS-Pfade (`/roms`, `/opt/system/Tools/PortMaster`,
  `~/.config/retroarch/retroarch.cfg`, `/etc/emulationstation/es_systems.cfg`).
- **Zwei Geräte:** `r36a` (Bastelgerät) und `r36b` (Referenz, unveränderte Karte). Änderungen zuerst nur auf r36a.

## Gerätezugriff

- SSH-Hosts `r36a`/`r36b` aus `ssh/config.example`, User `ark`. Vor jeder Arbeit an einem Gerät
  `scripts/inventory.sh <host>` – die Ergebnisse in `device/<host>/` sind die Wahrheit über Pfade, Kernel-Module,
  RetroArch-Konfig. Nie Pfade raten, immer aus `device/<host>/inventory.txt` bzw. `es_systems.cfg` ableiten.
- `device/` ist gitignored (gerätespezifisch). Keine Kopien davon committen.
- Auf dem Gerät nichts löschen oder überschreiben, was nicht vorher gesichert ist. `deploy.sh` legt
  `es_systems.cfg.orig` an; andere Systemdateien nur mit `.orig`-Kopie anfassen.
- Kein `apt upgrade` auf dem Gerät. Einzelne Pakete als arm64-`.deb` passend zu `lsb_release` per `dpkg -i`.

## Build

- Cross-Builds nur im Docker-Container (`docker/Dockerfile`, `scripts/build.sh`), Plattform `linux/arm64`.
  `UBUNTU` in `scripts/build.sh` muss zur ArkOS-Basis passen (`device/<host>/inventory.txt`, Zeile `lsb_release`).
- Auf dem Host darf `make -C cores/adl` als reiner Compile-Check laufen (x86), das Ergebnis geht nicht aufs Gerät.
- Binaries/`.so` sind gitignored. Libs, die das Gerät nicht hat, werden mit dem Port gebündelt (`ports/<name>/lib/`),
  nicht systemweit installiert.

## Konventionen

- Ports: ein Ordner unter `ports/<name>/`, Startscript nach PortMaster-Muster (`source control.txt`, `get_controls`,
  `$GPTOKEYB`, Log nach `log.txt` im Port-Ordner, `$ESUDO kill` am Ende). Select+Start beendet immer.
- ES-Systeme: ein Fragment pro System in `es/systems/<name>.xml`. `{{RA}}`/`{{CORES}}` als Platzhalter,
  `scripts/es-merge.py` ersetzt sie aus der Gerätedatei. Neue Systeme nutzen `theme="ports"`, bis Logos existieren.
- Cores: `cores/<name>/` mit `<name>_libretro.c`, `Makefile`, `<name>_libretro.info`. 48 kHz, 60 fps, 320×240 RGB565,
  MIDI direkt aus `/dev/snd/midiC*D*` (Override `<NAME>_MIDI_DEV`), kein RetroArch-MIDI-Interface.
- Shell: `set -euo pipefail` in Host-Scripts; Gerätescripts bleiben `bash` ohne `-e` (PortMaster-Umgebung).
- Sprache in Doku und Kommentaren: Deutsch. Commit-Messages: Englisch, kurz.

## Status

- Fertig, ungetestet auf Hardware: alle Scripts, ES-Fragmente, Port-Scripts, `cores/adl`.
- `cores/adl` ist auf x86 gebaut und per Harness geprüft (Bank laden, Noten via FIFO, Audio-Energie, Note-Off → Stille).
- Offen: Makefile-Name im Picoloop-Repo (`ports/picoloop/build.sh` listet Kandidaten), `LGPT_BIN`-Pfad
  (`ports/lgpt/lgpt.sh`), `gme_libretro.so` arm64 beschaffen (`cores/gme/`), Theme-Logos.
- Nächste Engines nach `adl`: `opn` (libOPNMIDI, `.wopn`), `mt32` (mt32emu, ROMs in RetroArch `system/`).

## Reihenfolge (nicht überspringen)

1. Phase 0: SSH via RNDIS auf r36a → `inventory.sh r36a`
2. Phase 1: USB-Ethernet am OTG-Hub, wenn `r8152`/`cdc_ether` laut Inventar vorhanden
3. Phase 2: `diag.sh r36a 20:0` zeigt MIDI-Noten
4. Phase 4.1: FluidSynth-System deployen → reale Latenz messen
5. Phase 4.2/4.3/4.4: GME, Picoloop, LGPT
6. Phase 5: `build.sh adl` → deploy → `run.sh` mit `retroarch -L … --verbose`

Details je Phase stehen in `README.md`. Bei Unklarheit über einen Gerätepfad: erst Inventar, dann fragen, nie raten.
