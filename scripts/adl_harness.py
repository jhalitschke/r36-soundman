#!/usr/bin/env python3
"""Fährt einen gebauten libretro-Core ohne RetroArch und ohne Gerät:
Callbacks per ctypes, MIDI über eine FIFO (ADL_MIDI_DEV), Audio in eine WAV.

    scripts/adl_harness.py --demo out.wav      # Demo-Sequenz rendern
    scripts/adl_harness.py --ton 69 out.wav    # Einzelnote (A4) rendern

Damit sind Bank, MIDI-Parser, Notenausgabe und Note-Off auf dem Host prüfbar
(x86-Build). Aufs Gerät geht das Ergebnis nicht – es ist ein Funktionstest.
"""
import argparse
import ctypes
import math
import os
import sys
import tempfile
import wave
from array import array
from pathlib import Path

SR = 48000
FRAMES = SR // 60          # ein retro_run = 800 Frames = 16,667 ms
ROOT = Path(__file__).resolve().parent.parent
SO = ROOT / "cores" / "adl" / "adl_libretro.so"

ENV_SET_PIXEL_FORMAT = 10
ENV_SET_SUPPORT_NO_GAME = 18
ENV_GET_LOG_INTERFACE = 27
ENV_SET_MINIMUM_AUDIO_LATENCY = 63

JOYPAD = 1
ID_A, ID_L, ID_R = 8, 10, 11

CB_ENV = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_uint, ctypes.c_void_p)
CB_VIDEO = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_size_t)
CB_AUDIO_BATCH = ctypes.CFUNCTYPE(ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t)
CB_AUDIO = ctypes.CFUNCTYPE(None, ctypes.c_int16, ctypes.c_int16)
CB_POLL = ctypes.CFUNCTYPE(None)
CB_STATE = ctypes.CFUNCTYPE(ctypes.c_int16, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint)


class Core:
    """Ein geladener libretro-Core mit FIFO als MIDI-Eingang."""

    def __init__(self, so=SO, bank=None):
        self.audio = array("h")          # interleaved stereo
        self.frames_vorher = 0           # Framezähler beim letzten Event
        self.buttons = set()
        self.video_calls = 0
        self._tmp = tempfile.mkdtemp(prefix="adl-harness-")
        self.fifo = os.path.join(self._tmp, "midi")
        os.mkfifo(self.fifo)
        os.environ["ADL_MIDI_DEV"] = self.fifo   # muss vor retro_load_game stehen

        self.lib = ctypes.CDLL(str(so))
        self.lib.retro_load_game.restype = ctypes.c_bool
        self.lib.retro_load_game.argtypes = [ctypes.c_void_p]

        # Referenzen halten, sonst sammelt der GC die Callbacks ein.
        self._cbs = [CB_ENV(self._env), CB_VIDEO(self._video), CB_AUDIO_BATCH(self._audio_batch),
                     CB_AUDIO(lambda l, r: None), CB_POLL(lambda: None), CB_STATE(self._state)]
        self.lib.retro_set_environment(self._cbs[0])
        self.lib.retro_set_video_refresh(self._cbs[1])
        self.lib.retro_set_audio_sample_batch(self._cbs[2])
        self.lib.retro_set_audio_sample(self._cbs[3])
        self.lib.retro_set_input_poll(self._cbs[4])
        self.lib.retro_set_input_state(self._cbs[5])
        self.lib.retro_init()

        arg = ctypes.c_char_p(str(bank).encode()) if bank else None
        if not self.lib.retro_load_game(arg):
            raise SystemExit("retro_load_game fehlgeschlagen")
        self.midi = os.open(self.fifo, os.O_WRONLY | os.O_NONBLOCK)

    # --- libretro-Callbacks ---
    def _env(self, cmd, data):
        if cmd == ENV_SET_PIXEL_FORMAT:
            return True                      # RGB565 akzeptieren
        if cmd in (ENV_SET_SUPPORT_NO_GAME, ENV_SET_MINIMUM_AUDIO_LATENCY):
            return True
        if cmd == ENV_GET_LOG_INTERFACE:
            return False                     # Core nimmt dann seinen stderr-Fallback
        return False

    def _video(self, data, w, h, pitch):
        self.video_calls += 1

    def _audio_batch(self, data, frames):
        if data and frames:
            self.audio.frombytes(ctypes.string_at(data, int(frames) * 4))
        return frames

    def _state(self, port, device, index, id_):
        return 1 if (device == JOYPAD and id_ in self.buttons) else 0

    # --- Steuerung ---
    @property
    def frames(self):
        return len(self.audio) // 2

    def send(self, *bytes_):
        os.write(self.midi, bytes(bytes_))

    def note_on(self, ch, note, vel=100):
        self.send(0x90 | ch, note, vel)

    def note_off(self, ch, note):
        self.send(0x80 | ch, note, 0)

    def program(self, ch, prog):
        self.send(0xC0 | ch, prog)

    def run(self, n=1):
        for _ in range(n):
            self.lib.retro_run()

    def taste(self, id_):
        """Einen Frame lang drücken, einen loslassen (der Core sieht die Flanke)."""
        self.buttons.add(id_)
        self.run()
        self.buttons.discard(id_)
        self.run()

    def close(self):
        os.close(self.midi)
        self.lib.retro_unload_game()
        self.lib.retro_deinit()
        os.unlink(self.fifo)
        os.rmdir(self._tmp)

    def wav(self, pfad):
        with wave.open(str(pfad), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(self.audio.tobytes())
        return pfad


# --- Auswertung ----------------------------------------------------------
def mono(audio, von=0, bis=None):
    bis = len(audio) // 2 if bis is None else bis
    return [(audio[2 * i] + audio[2 * i + 1]) / 2.0 for i in range(von, bis)]


def rms(samples):
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


def peak(audio):
    return max((abs(s) for s in audio), default=0)


def clip_anteil(audio):
    """Anteil der Samples an der Saettigungsgrenze – zu viel heisst: Gain runter."""
    if not audio:
        return 0.0
    return sum(1 for s in audio if s >= 32767 or s <= -32768) / len(audio)


def grundfrequenz(samples, sr=SR, fmin=60.0, fmax=1500.0):
    """Grundton per normierter Autokorrelation (ohne numpy).

    Normiert wird auf die Energie beider Fenster, sonst gewinnen lange Lags.
    Danach der kleinste Lag, der noch 85 % des Maximums erreicht – das ist der
    Grundton und nicht dessen Subharmonische (FM-Timbres sind obertonreich).
    """
    n = len(samples)
    mittel = sum(samples) / n
    x = [s - mittel for s in samples]
    quad = [0.0] * (n + 1)                       # Prefix-Summe der Quadrate
    for i, v in enumerate(x):
        quad[i + 1] = quad[i] + v * v
    lag_min, lag_max = max(2, int(sr / fmax)), min(int(sr / fmin), n // 2)
    korr = {}
    for lag in range(lag_min, lag_max + 1):
        m = n - lag
        e1, e2 = quad[m] - quad[0], quad[n] - quad[lag]
        if e1 <= 0 or e2 <= 0:
            continue
        summe = sum(x[i] * x[i + lag] for i in range(m))
        korr[lag] = summe / math.sqrt(e1 * e2)
    if not korr:
        return 0.0
    best = max(korr.values())
    if best <= 0:
        return 0.0
    lag = min(l for l, r in korr.items() if r >= 0.85 * best)
    while lag + 1 in korr and korr[lag + 1] > korr[lag]:
        lag += 1                                 # auf das lokale Maximum laufen
    y0, y1, y2 = korr.get(lag - 1, 0.0), korr[lag], korr.get(lag + 1, 0.0)
    nenner = y0 - 2 * y1 + y2
    versatz = (y0 - y2) / (2 * nenner) if nenner else 0.0   # Subsample-Genauigkeit
    return sr / (lag + max(-0.5, min(0.5, versatz)))


def note_hz(note):
    return 440.0 * 2 ** ((note - 69) / 12.0)


# --- Demo ----------------------------------------------------------------
BPM = 120
FRAMES_PRO_BEAT = int(SR * 60 / BPM)     # 24000

LEAD, BASS, PAD, DRUM = 0, 1, 2, 9
PROGRAMME = {LEAD: 81, BASS: 38, PAD: 89}   # Saw Lead, Synth Bass 1, Warm Pad

# (Takt, Beat, Kanal, Note, Dauer in Beats, Velocity)
AKKORDE = {0: (48, 51, 55), 1: (44, 48, 51), 2: (51, 55, 58), 3: (46, 50, 53)}  # Cm Ab Eb Bb
RIFF = [  # (Beat im Takt, Note, Dauer)
    (0.0, 72, 0.5), (0.5, 70, 0.5), (1.0, 67, 0.5), (1.5, 63, 0.5),
    (2.0, 65, 0.75), (3.0, 67, 1.0),
]
RIFF_B = [
    (0.0, 75, 0.5), (0.5, 72, 0.5), (1.0, 70, 1.0), (2.0, 67, 0.5),
    (2.5, 70, 0.5), (3.0, 72, 1.0),
]


def demo_events(takte=6):
    """Liste (frame, callable-Name, args) – wird vom Renderer abgespielt."""
    ev = []

    def on(beat, ch, note, vel=100):
        ev.append((int(beat * FRAMES_PRO_BEAT), "note_on", (ch, note, vel)))

    def off(beat, ch, note):
        ev.append((int(beat * FRAMES_PRO_BEAT), "note_off", (ch, note)))

    def spiel(beat, ch, note, dauer, vel=100):
        on(beat, ch, note, vel)
        off(beat + dauer * 0.9, ch, note)

    for takt in range(takte):
        t0 = takt * 4
        grund = AKKORDE[takt % 4][0] - 12        # Bass eine Oktave tiefer
        # Bass: Achtel-Puls auf dem Grundton, Takt 4 als Fill
        for i in range(8):
            spiel(t0 + i * 0.5, BASS, grund if i % 4 else grund + 12, 0.45, 110)
        # Pad: Akkord über den ganzen Takt
        for note in AKKORDE[takt % 4]:
            spiel(t0, PAD, note, 3.8, 70)
        # Lead: ab Takt 2, letzter Takt mit Variante
        if takt >= 1:
            for beat, note, dauer in (RIFF_B if takt % 2 else RIFF):
                spiel(t0 + beat, LEAD, note, dauer, 105)
        # Drums: Kick 1+3, Snare 2+4, Hi-Hat auf Achteln
        for i in range(4):
            spiel(t0 + i, DRUM, 36 if i % 2 == 0 else 38, 0.2, 110)
        for i in range(8):
            spiel(t0 + i * 0.5, DRUM, 42, 0.1, 70 if i % 2 else 90)
    return sorted(ev)


def render(events, takte_frames, core):
    """Events framegenau zwischen die retro_run-Aufrufe schieben."""
    events = list(events)
    while core.frames < takte_frames:
        jetzt = core.frames
        while events and events[0][0] <= jetzt + FRAMES:
            _, name, args = events.pop(0)
            getattr(core, name)(*args)
        core.run()
    return core


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("wav", nargs="?", help="Ausgabedatei")
    p.add_argument("--so", default=str(SO), help="Core (.so)")
    p.add_argument("--bank", help=".wopl-Bank (ohne: eingebettete Bank 0)")
    p.add_argument("--demo", action="store_true", help="Demo-Sequenz (6 Takte, 120 bpm)")
    p.add_argument("--ton", type=int, metavar="NOTE", help="eine MIDI-Note 2 s lang")
    p.add_argument("--programm", type=int, default=81, help="Program für --ton (Standard 81)")
    a = p.parse_args(argv)

    core = Core(a.so, a.bank)
    try:
        if a.ton is not None:
            core.program(LEAD, a.programm)
            core.run(2)
            core.note_on(LEAD, a.ton, 110)
            core.run(120)                     # 2 s
            core.note_off(LEAD, a.ton)
            core.run(30)                      # 0,5 s Ausklang
            print("Note %d = %.2f Hz erwartet, gemessen %.2f Hz"
                  % (a.ton, note_hz(a.ton), grundfrequenz(mono(core.audio, SR // 4, SR // 4 + 4096))))
        else:
            for ch, prog in PROGRAMME.items():
                core.program(ch, prog)
            core.run(2)
            takte = 6
            render(demo_events(takte), takte * 4 * FRAMES_PRO_BEAT, core)
            core.run(60)                      # 1 s ausklingen
        dauer = core.frames / SR
        print("%.2f s, %d retro_run-Aufrufe, Peak %d (%.1f dBFS), RMS %.0f, Clipping %.3f %%"
              % (dauer, core.video_calls, peak(core.audio),
                 20 * math.log10(max(peak(core.audio), 1) / 32768.0), rms(mono(core.audio)),
                 100 * clip_anteil(core.audio)))
        if a.wav:
            print("-> " + str(core.wav(a.wav)))
    finally:
        core.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
