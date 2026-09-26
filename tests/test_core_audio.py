#!/usr/bin/env python3
"""Testing the built core without ears or a screen: audio and framebuffer.

Needs cores/adl/adl_libretro.so (make -C cores/adl) - without it the tests skip
themselves, so the lint job stays build-free.
"""
import importlib.util
import os
import tempfile
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


@unittest.skipUnless(SO.exists(), "cores/adl/adl_libretro.so missing - run 'make -C cores/adl' first")
class TestCoreScreen(unittest.TestCase):
    """The 320x240 framebuffer is the only feedback the device gives, so check it."""

    def test_status_field_is_green_with_midi(self):
        core = H.Core(SO, midi=True)
        self.addCleanup(core.close)
        self.assertEqual(H.pixel(core.screenshot(), 10, 10), H.GREEN)

    def test_status_field_is_red_without_midi(self):
        core = H.Core(SO, midi=False)
        self.addCleanup(core.close)
        self.assertEqual(H.pixel(core.screenshot(), 10, 10), H.RED)

    def test_notes_light_up_their_channel_bars(self):
        core = H.Core(SO)
        self.addCleanup(core.close)
        empty = core.screenshot()
        self.assertEqual(H.pixel(empty, 10, 215), 0x0000, "bars light up without a note")
        core.note_on(H.LEAD, 69, 110)
        core.note_on(H.DRUM, 36, 110)
        shot = core.screenshot()
        self.assertEqual(H.pixel(shot, 10, 215), H.CHAN_BAR)
        self.assertEqual(H.pixel(shot, 8 + 9 * 19 + 2, 215), H.DRUM_BAR, "channel 10 is not drawn as drums")

    def test_program_bar_grows_with_the_r_button(self):
        core = H.Core(SO)
        self.addCleanup(core.close)
        before = core.screenshot()
        for _ in range(8):
            core.press(H.ID_R)
        after = core.screenshot()
        def bar_width(shot):
            return sum(1 for x in range(24, 200) if H.pixel(shot, x, 10) == H.WHITE)
        self.assertGreater(bar_width(after), bar_width(before), "program bar does not grow")

    def test_screenshot_is_a_valid_png(self):
        core = H.Core(SO)
        self.addCleanup(core.close)
        w, h, fb = core.screenshot()
        self.assertEqual((w, h, len(fb)), (320, 240, 320 * 240 * 2))
        with tempfile.TemporaryDirectory() as d:
            path = H.png(os.path.join(d, "s.png"), w, h, fb, scale=1)
            data = Path(path).read_bytes()
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertIn(b"IEND", data[-12:])


if __name__ == "__main__":
    unittest.main()
