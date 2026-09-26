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
        self.addCleanup(os.environ.pop, "ADL_GAIN", None)
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


@unittest.skipUnless(SO.exists(), "cores/adl/adl_libretro.so missing - run 'make -C cores/adl' first")
class TestCoreMidi(unittest.TestCase):
    """The wire format, not just the three messages the harness has helpers for.

    A USB MIDI keyboard mostly sends running status, note-off as velocity 0 and
    realtime bytes in between, so those paths carry the instrument.
    """

    def core(self):
        core = H.Core(SO)
        self.addCleanup(core.close)
        core.program(H.LEAD, 81)
        core.run(6)
        return core

    def sounding(self, core, start, runs=45):
        core.run(runs)
        return H.rms(H.mono(core.audio, start + H.SR // 50))

    def test_running_status_plays_the_second_note(self):
        core = self.core()
        start = core.frames
        core.send(0x90, 60, 100)          # status byte once
        core.send(64, 100)                # running status: data bytes only
        core.send(0x80, 60, 0)            # silence the first one again
        self.assertGreater(self.sounding(core, start), 200.0, "running status note is missing")

    def test_data_bytes_without_a_status_byte_are_ignored(self):
        core = self.core()
        start = core.frames
        core.send(64, 100)                # no status has ever been sent
        self.assertLess(self.sounding(core, start), 1.0, "parser invents a note")

    def test_note_on_with_velocity_zero_is_a_note_off(self):
        core = self.core()
        start = core.frames
        core.send(0x90, 69, 110)
        loud = self.sounding(core, start)
        off = core.frames
        core.send(0x90, 69, 0)            # the usual note-off from a keyboard
        core.run(45)
        self.assertLess(H.rms(H.mono(core.audio, off + H.SR // 2)), loud * 0.05)

    def test_controller_all_notes_off(self):
        core = self.core()
        start = core.frames
        core.send(0x90, 69, 110)
        loud = self.sounding(core, start)
        off = core.frames
        core.send(0xB0, 123, 0)           # CC 123 = all notes off
        core.run(45)
        self.assertLess(H.rms(H.mono(core.audio, off + H.SR // 2)), loud * 0.05)

    def test_pitch_bend_raises_the_pitch(self):
        core = self.core()
        core.send(0x90, 69, 110)
        core.run(45)
        flat = H.fundamental(H.mono(core.audio, core.frames - 8192, core.frames - 4096))
        core.send(0xE0, 0x00, 0x60)       # lsb, msb - half of the upward range
        core.run(45)
        bent = H.fundamental(H.mono(core.audio, core.frames - 8192, core.frames - 4096))
        self.assertGreater(bent / flat, 1.03, "pitch bend does nothing (%.1f -> %.1f Hz)" % (flat, bent))

    def test_realtime_bytes_do_not_disturb_the_parser(self):
        """Active sensing arrives constantly, including inside a message."""
        core = self.core()
        start = core.frames
        core.send(0x90, 60)               # message cut in half
        core.send(0xFE)                   # active sensing right in the middle
        core.send(100)                    # completes note-on 60
        core.send(0xFE)
        core.send(64, 100)                # running status is still 0x90
        self.assertGreater(self.sounding(core, start), 200.0, "realtime byte swallowed the note")

    def test_sysex_is_skipped_and_ends_running_status(self):
        core = self.core()
        start = core.frames
        core.send(0xF0, 0x7E, 0x7F, 0x09, 0x01, 0xF7)   # GM reset
        core.send(69, 110)                # must be ignored: sysex cleared the status
        self.assertLess(self.sounding(core, start), 1.0, "data bytes after sysex were played")
        start = core.frames
        core.send(0x90, 69, 110)          # a full message still works
        self.assertGreater(self.sounding(core, start), 200.0)


@unittest.skipUnless(SO.exists(), "cores/adl/adl_libretro.so missing - run 'make -C cores/adl' first")
class TestCoreBank(unittest.TestCase):
    """retro_load_game with content - the path CLAUDE.md claims is covered."""

    BANK = ROOT / "cores" / "adl" / "libADLMIDI" / "fm_banks" / "ail" / "MonopolyDeluxe.wopl"

    def play(self, core):
        core.program(H.LEAD, 81)
        core.run(6)
        start = core.frames
        core.note_on(H.LEAD, 69, 110)
        core.run(45)
        return H.rms(H.mono(core.audio, start + H.SR // 50))

    @unittest.skipUnless(BANK.exists(), "no .wopl in the libADLMIDI checkout")
    def test_wopl_bank_loads_and_sounds(self):
        core = H.Core(SO, bank=self.BANK)
        self.addCleanup(core.close)
        self.assertGreater(self.play(core), 200.0)

    def test_empty_marker_falls_back_to_the_embedded_bank(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / "embedded.wopl"
            marker.touch()
            core = H.Core(SO, bank=marker)
            self.addCleanup(core.close)
            self.assertGreater(self.play(core), 200.0)

    def test_a_broken_bank_fails_loudly(self):
        with tempfile.TemporaryDirectory() as d:
            broken = Path(d) / "broken.wopl"
            broken.write_bytes(b"not a bank")
            with self.assertRaises(SystemExit):
                H.Core(SO, bank=broken)


if __name__ == "__main__":
    unittest.main()
