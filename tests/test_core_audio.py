#!/usr/bin/env python3
"""Listening test without ears: drives the built core and checks its audio.

Needs cores/adl/adl_libretro.so (make -C cores/adl) - without it the tests skip
themselves, so the lint job stays build-free.
"""
import importlib.util
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SO = ROOT / "cores" / "adl" / "adl_libretro.so"


def _harness():
    spec = importlib.util.spec_from_file_location("adl_harness", ROOT / "scripts" / "adl_harness.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


H = _harness() if SO.exists() else None


@unittest.skipUnless(SO.exists(), "cores/adl/adl_libretro.so missing - run 'make -C cores/adl' first")
class TestCoreAudio(unittest.TestCase):
    def setUp(self):
        os.environ.pop("ADL_GAIN", None)
        self.core = H.Core(SO)
        self.addCleanup(self.core.close)

    def play(self, note=69, program=81, runs=90):
        """Play a note, return (rms before, rms while sounding, start frame)."""
        self.core.program(H.LEAD, program)
        self.core.run(6)
        before = H.rms(H.mono(self.core.audio))
        start = self.core.frames
        self.core.note_on(H.LEAD, note, 110)
        self.core.run(runs)
        sounding = H.rms(H.mono(self.core.audio, start + H.SR // 50))
        return before, sounding, start

    def test_silent_before_the_first_note(self):
        self.core.run(6)
        self.assertLess(H.rms(H.mono(self.core.audio)), 1.0, "the core hisses without a note")

    def test_note_produces_energy(self):
        before, sounding, _ = self.play()
        self.assertLess(before, 1.0)
        self.assertGreater(sounding, 200.0, "note-on barely produces a level")

    def test_pitch_is_correct(self):
        for note in (60, 69, 72):
            with self.subTest(note=note):
                core = H.Core(SO)
                self.addCleanup(core.close)
                core.program(H.LEAD, 81)
                core.run(6)
                core.note_on(H.LEAD, note, 110)
                core.run(60)
                start = H.SR // 4
                hz = H.fundamental(H.mono(core.audio, start, start + 4096))
                expected = H.note_hz(note)
                self.assertAlmostEqual(hz / expected, 1.0, delta=0.01,
                                       msg="note %d: %.1f Hz instead of %.1f Hz" % (note, hz, expected))

    def test_note_off_goes_quiet(self):
        _, sounding, _ = self.play()
        after_off = self.core.frames
        self.core.note_off(H.LEAD, 69)
        self.core.run(45)                                  # 0.75 s of release
        tail = H.rms(H.mono(self.core.audio, after_off + H.SR // 2))
        self.assertLess(tail, sounding * 0.05, "note-off does not release")

    def test_panic_goes_quiet(self):
        _, sounding, _ = self.play()
        self.core.press(H.ID_A)                            # A = adl_panic
        after = self.core.frames
        self.core.run(30)
        self.assertLess(H.rms(H.mono(self.core.audio, after + H.SR // 4)), sounding * 0.05,
                        "panic does not silence the core")

    def test_program_change_by_button(self):
        self.core.press(H.ID_R)
        self.core.press(H.ID_L)
        start = self.core.frames
        self.core.note_on(H.LEAD, 69, 110)
        self.core.run(60)
        self.assertGreater(H.rms(H.mono(self.core.audio, start + H.SR // 50)), 200.0,
                           "no sound left after L/R")

    def test_gain_scales_and_does_not_clip(self):
        """ADL_GAIN scales linearly; a single note must not saturate."""
        levels = {}
        for gain in ("1", "6"):
            os.environ["ADL_GAIN"] = gain
            core = H.Core(SO)
            self.addCleanup(core.close)
            core.program(H.LEAD, 81)
            core.run(6)
            core.note_on(H.LEAD, 69, 110)
            core.run(60)
            levels[gain] = H.peak(core.audio)
            self.assertEqual(H.clip_ratio(core.audio), 0.0, "a single note clips at gain %s" % gain)
        os.environ.pop("ADL_GAIN", None)
        self.assertAlmostEqual(levels["6"] / levels["1"], 6.0, delta=0.6,
                               msg="gain is not linear: %r" % levels)


if __name__ == "__main__":
    unittest.main()
