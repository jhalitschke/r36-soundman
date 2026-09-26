#!/usr/bin/env python3
"""Drives a built libretro core without RetroArch and without the device:
callbacks via ctypes, MIDI through a FIFO (ADL_MIDI_DEV), audio into a WAV.

    scripts/adl_harness.py --demo out.wav      # render the demo sequence
    scripts/adl_harness.py --tone 69 out.wav   # render a single note (A4)
    scripts/adl_harness.py --demo --shots shot # the core's own 320x240 screen as PNGs

That makes the bank, the MIDI parser, note output and note-off verifiable on the
host (x86 build). The result does not go to the device - it is a functional test.
"""
import argparse
import ctypes
import math
import os
import struct
import sys
import tempfile
import wave
import zlib
from array import array
from pathlib import Path

SR = 48000
FRAMES = SR // 60          # one retro_run = 800 frames = 16.667 ms
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
    """A loaded libretro core with a FIFO as its MIDI input."""

    def __init__(self, so=SO, bank=None, midi=True):
        self.audio = array("h")          # interleaved stereo
        self.buttons = set()
        self.video_calls = 0
        self.shot_at = set()             # video-callback numbers to capture
        self.shots = []                  # captured (width, height, RGB565 bytes)
        self._tmp = tempfile.mkdtemp(prefix="adl-harness-")
        self.fifo = os.path.join(self._tmp, "midi")
        os.mkfifo(self.fifo)
        # Has to be set before retro_load_game. midi=False points the core at a path
        # that does not exist, which is how the "no rawmidi device" state is reached.
        os.environ["ADL_MIDI_DEV"] = self.fifo if midi else self.fifo + "-absent"

        self.lib = ctypes.CDLL(str(so))
        self.lib.retro_load_game.restype = ctypes.c_bool
        self.lib.retro_load_game.argtypes = [ctypes.c_void_p]

        # Keep the references, otherwise the GC collects the callbacks.
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
            raise SystemExit("retro_load_game failed")
        # O_RDWR, not O_WRONLY: with midi=False nobody opened the read end, and
        # opening a FIFO write-only without a reader fails with ENXIO.
        self.midi = os.open(self.fifo, os.O_RDWR | os.O_NONBLOCK)

    # --- libretro callbacks ---
    def _env(self, cmd, data):
        if cmd == ENV_SET_PIXEL_FORMAT:
            return True                      # accept RGB565
        if cmd in (ENV_SET_SUPPORT_NO_GAME, ENV_SET_MINIMUM_AUDIO_LATENCY):
            return True
        if cmd == ENV_GET_LOG_INTERFACE:
            return False                     # the core then uses its stderr fallback
        return False

    def _video(self, data, w, h, pitch):
        self.video_calls += 1
        if self.video_calls in self.shot_at and data:
            rows = [ctypes.string_at(data + y * pitch, w * 2) for y in range(h)]
            self.shots.append((w, h, b"".join(rows)))

    def _audio_batch(self, data, frames):
        if data and frames:
            self.audio.frombytes(ctypes.string_at(data, int(frames) * 4))
        return frames

    def _state(self, port, device, index, id_):
        return 1 if (device == JOYPAD and id_ in self.buttons) else 0

    # --- control ---
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

    def screenshot(self):
        """Run one frame and return its framebuffer as (width, height, RGB565 bytes)."""
        self.shot_at = {self.video_calls + 1}
        self.run()
        self.shot_at = set()
        return self.shots[-1]

    def press(self, id_):
        """Hold for one frame, release for one, so the core sees the edge."""
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

    def wav(self, path):
        with wave.open(str(path), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(self.audio.tobytes())
        return path


def pixel(shot, x, y):
    """One RGB565 value out of a captured framebuffer."""
    width, _, fb = shot
    i = 2 * (y * width + x)
    return fb[i] | (fb[i + 1] << 8)


# Colours the core draws with (see draw() in adl_libretro.c).
GREEN, RED, WHITE, DRUM_BAR, CHAN_BAR = 0x07E0, 0xF800, 0xFFFF, 0xFD20, 0x3D9F


def png(path, width, height, rgb565, scale=3):
    """Write an RGB565 framebuffer as a PNG, nearest-neighbour scaled (no deps)."""
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            v = rgb565[2 * (y * width + x)] | (rgb565[2 * (y * width + x) + 1] << 8)
            rgb = bytes((((v >> 11) & 0x1F) * 255 // 31,
                         ((v >> 5) & 0x3F) * 255 // 63,
                         (v & 0x1F) * 255 // 31))
            row += rgb * scale
        rows.extend([bytes(row)] * scale)
    raw = b"".join(b"\x00" + r for r in rows)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    head = struct.pack(">IIBBBBB", width * scale, height * scale, 8, 2, 0, 0, 0)
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head)
                           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    return path


# --- analysis ------------------------------------------------------------
def mono(audio, start=0, end=None):
    end = len(audio) // 2 if end is None else end
    return [(audio[2 * i] + audio[2 * i + 1]) / 2.0 for i in range(start, end)]


def rms(samples):
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


def peak(audio):
    return max((abs(s) for s in audio), default=0)


def clip_ratio(audio):
    """Fraction of samples at the saturation limit - too many means turn the gain down."""
    if not audio:
        return 0.0
    return sum(1 for s in audio if s >= 32767 or s <= -32768) / len(audio)


def fundamental(samples, sr=SR, fmin=60.0, fmax=1500.0):
    """Fundamental via normalized autocorrelation (no numpy).

    Normalizing by the energy of both windows keeps long lags from winning.
    Then take the smallest lag that still reaches 85 % of the maximum - that is
    the fundamental and not one of its subharmonics (FM timbres are rich in
    overtones).
    """
    n = len(samples)
    mean = sum(samples) / n
    x = [s - mean for s in samples]
    squares = [0.0] * (n + 1)                    # prefix sum of squares
    for i, v in enumerate(x):
        squares[i + 1] = squares[i] + v * v
    lag_min, lag_max = max(2, int(sr / fmax)), min(int(sr / fmin), n // 2)
    corr = {}
    for lag in range(lag_min, lag_max + 1):
        m = n - lag
        e1, e2 = squares[m] - squares[0], squares[n] - squares[lag]
        if e1 <= 0 or e2 <= 0:
            continue
        total = sum(x[i] * x[i + lag] for i in range(m))
        corr[lag] = total / math.sqrt(e1 * e2)
    if not corr:
        return 0.0
    best = max(corr.values())
    if best <= 0:
        return 0.0
    lag = min(l for l, r in corr.items() if r >= 0.85 * best)
    while lag + 1 in corr and corr[lag + 1] > corr[lag]:
        lag += 1                                 # walk up to the local maximum
    y0, y1, y2 = corr.get(lag - 1, 0.0), corr[lag], corr.get(lag + 1, 0.0)
    denom = y0 - 2 * y1 + y2
    offset = (y0 - y2) / (2 * denom) if denom else 0.0   # sub-sample accuracy
    return sr / (lag + max(-0.5, min(0.5, offset)))


def note_hz(note):
    return 440.0 * 2 ** ((note - 69) / 12.0)


# --- demo ----------------------------------------------------------------
BPM = 120
FRAMES_PER_BEAT = int(SR * 60 / BPM)     # 24000

LEAD, BASS, PAD, DRUM = 0, 1, 2, 9
PROGRAMS = {LEAD: 81, BASS: 38, PAD: 89}   # saw lead, synth bass 1, warm pad

CHORDS = {0: (48, 51, 55), 1: (44, 48, 51), 2: (51, 55, 58), 3: (46, 50, 53)}  # Cm Ab Eb Bb
RIFF = [  # (beat within the bar, note, length in beats)
    (0.0, 72, 0.5), (0.5, 70, 0.5), (1.0, 67, 0.5), (1.5, 63, 0.5),
    (2.0, 65, 0.75), (3.0, 67, 1.0),
]
RIFF_B = [
    (0.0, 75, 0.5), (0.5, 72, 0.5), (1.0, 70, 1.0), (2.0, 67, 0.5),
    (2.5, 70, 0.5), (3.0, 72, 1.0),
]


def demo_events(bars=6):
    """List of (frame, method name, args) - played back by the renderer."""
    ev = []

    def on(beat, ch, note, vel=100):
        ev.append((int(beat * FRAMES_PER_BEAT), "note_on", (ch, note, vel)))

    def off(beat, ch, note):
        ev.append((int(beat * FRAMES_PER_BEAT), "note_off", (ch, note)))

    def play(beat, ch, note, length, vel=100):
        on(beat, ch, note, vel)
        off(beat + length * 0.9, ch, note)

    for bar in range(bars):
        t0 = bar * 4
        root = CHORDS[bar % 4][0] - 12           # bass an octave lower
        # Bass: eighth-note pulse on the root, with an octave jump as a fill
        for i in range(8):
            play(t0 + i * 0.5, BASS, root if i % 4 else root + 12, 0.45, 110)
        # Pad: the chord across the whole bar
        for note in CHORDS[bar % 4]:
            play(t0, PAD, note, 3.8, 70)
        # Lead: from bar 2 on, alternating variant
        if bar >= 1:
            for beat, note, length in (RIFF_B if bar % 2 else RIFF):
                play(t0 + beat, LEAD, note, length, 105)
        # Drums: kick on 1+3, snare on 2+4, hi-hat on eighths
        for i in range(4):
            play(t0 + i, DRUM, 36 if i % 2 == 0 else 38, 0.2, 110)
        for i in range(8):
            play(t0 + i * 0.5, DRUM, 42, 0.1, 70 if i % 2 else 90)
    return sorted(ev)


def render(events, runs, core):
    """Feed the events frame-accurately between exactly `runs` retro_run calls."""
    events = list(events)
    for _ in range(runs):
        now = core.frames
        while events and events[0][0] <= now + FRAMES:
            _, name, args = events.pop(0)
            getattr(core, name)(*args)
        core.run()
    return core


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("wav", nargs="?", help="output file")
    p.add_argument("--so", default=str(SO), help="core (.so)")
    p.add_argument("--bank", help=".wopl bank (without it: embedded bank 0)")
    p.add_argument("--demo", action="store_true", help="demo sequence (6 bars, 120 bpm)")
    p.add_argument("--tone", type=int, metavar="NOTE", help="one MIDI note for 2 s")
    p.add_argument("--program", type=int, default=81, help="program for --tone (default 81)")
    p.add_argument("--shots", metavar="PREFIX", help="write 4 PNGs of the core's screen (<PREFIX>-1.png ...)")
    p.add_argument("--scale", type=int, default=3, help="PNG scale factor (default 3 -> 960x720)")
    a = p.parse_args(argv)

    core = Core(a.so, a.bank)
    bars, pre, post = 6, 2, 60
    main_runs = bars * 4 * FRAMES_PER_BEAT // FRAMES
    runs = pre + (30 + 120 if a.tone is not None else main_runs) + post
    if a.shots:
        core.shot_at = {runs * i // 4 for i in range(1, 5)}
    try:
        if a.tone is not None:
            core.program(LEAD, a.program)
            core.run(pre)
            core.note_on(LEAD, a.tone, 110)
            core.run(120)                     # 2 s
            core.note_off(LEAD, a.tone)
            core.run(post)                    # 1 s of release
            print("note %d = %.2f Hz expected, %.2f Hz measured"
                  % (a.tone, note_hz(a.tone), fundamental(mono(core.audio, SR // 4, SR // 4 + 4096))))
        else:
            for ch, prog in PROGRAMS.items():
                core.program(ch, prog)
            core.run(pre)
            render(demo_events(bars), main_runs, core)
            core.run(post)                    # 1 s of release
        print("%.2f s, %d retro_run calls, peak %d (%.1f dBFS), RMS %.0f, clipping %.3f %%"
              % (core.frames / SR, core.video_calls, peak(core.audio),
                 20 * math.log10(max(peak(core.audio), 1) / 32768.0), rms(mono(core.audio)),
                 100 * clip_ratio(core.audio)))
        if a.wav:
            print("-> " + str(core.wav(a.wav)))
        for i, (w, h, fb) in enumerate(core.shots, 1):
            print("-> " + str(png("%s-%d.png" % (a.shots, i), w, h, fb, a.scale)))
    finally:
        core.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
