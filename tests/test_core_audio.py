#!/usr/bin/env python3
"""Testing the built cores without ears or a screen: audio and framebuffer.

Every core in cores/ follows the same conventions and a new one is a copy of an
existing one, so the same tests run against all of them - a copy is exactly
where a MIDI-parser or gain bug would go unnoticed. Without a built .so the
tests skip themselves, so the lint job stays build-free.
"""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Cores that cannot start without content, and the bank the tests hand them.
BANKS = {"opn": ROOT / "cores" / "opn" / "libOPNMIDI" / "fm_banks" / "xg.wopn"}


def cores():
    """(name, .so, bank) for every built core whose prerequisites are there."""
    for so in sorted(ROOT.glob("cores/*/*_libretro.so")):
        name = so.stem.replace("_libretro", "")
        bank = BANKS.get(name)
        if bank is not None and not bank.exists():
            continue
        yield name, so, bank


BUILT = list(cores())


def _harness():
    spec = importlib.util.spec_from_file_location("adl_harness", ROOT / "scripts" / "adl_harness.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


H = _harness() if BUILT else None


@unittest.skipUnless(BUILT, "no built core - run 'make -C cores/adl' first")
class CoreCase(unittest.TestCase):
    """Base class: run the test body once per built core."""

    def each_core(self, **kw):
        for name, so, bank in BUILT:
            with self.subTest(core=name):
                core = H.Core(so, bank=bank, **kw)
                self.addCleanup(core.close)
                yield name, core

    def play(self, core, note=69, program=81, runs=45):
        """Program change, note on, return the rms while it sounds."""
        core.program(H.LEAD, program)
        core.run(6)
        start = core.frames
        core.note_on(H.LEAD, note, 110)
        core.run(runs)
        return start, H.rms(H.mono(core.audio, start + H.SR // 50))


class TestCoreAudio(CoreCase):
    def test_silent_before_the_first_note(self):
        for _, core in self.each_core():
            core.run(6)
            self.assertLess(H.rms(H.mono(core.audio)), 1.0, "the core hisses without a note")

    def test_note_produces_energy(self):
        for _, core in self.each_core():
            _, sounding = self.play(core)
            self.assertGreater(sounding, 200.0, "note-on barely produces a level")

    def test_pitch_is_correct(self):
        for _, core in self.each_core():
            for note in (60, 69, 72):
                core.program(H.LEAD, 81)
                core.run(6)
                core.note_on(H.LEAD, note, 110)
                core.run(60)
                hz = H.fundamental(H.mono(core.audio, core.frames - 8192, core.frames - 4096))
                expected = H.note_hz(note)
                self.assertAlmostEqual(hz / expected, 1.0, delta=0.01,
                                       msg="note %d: %.1f Hz instead of %.1f Hz" % (note, hz, expected))
                core.note_off(H.LEAD, note)
                core.run(45)

    def test_note_off_goes_quiet(self):
        for _, core in self.each_core():
            _, sounding = self.play(core)
            after_off = core.frames
            core.note_off(H.LEAD, 69)
            core.run(45)                                   # 0.75 s of release
            self.assertLess(H.rms(H.mono(core.audio, after_off + H.SR // 2)), sounding * 0.05,
                            "note-off does not release")

    def test_panic_goes_quiet(self):
        for _, core in self.each_core():
            _, sounding = self.play(core)
            core.press(H.ID_A)                             # A = panic
            after = core.frames
            core.run(30)
            self.assertLess(H.rms(H.mono(core.audio, after + H.SR // 4)), sounding * 0.05,
                            "panic does not silence the core")

    def test_program_change_by_button(self):
        for _, core in self.each_core():
            core.press(H.ID_R)
            core.press(H.ID_L)
            start = core.frames
            core.note_on(H.LEAD, 69, 110)
            core.run(60)
            self.assertGreater(H.rms(H.mono(core.audio, start + H.SR // 50)), 200.0,
                               "no sound left after L/R")

    def test_gain_scales_and_does_not_clip(self):
        """<CORE>_GAIN scales linearly; a single note must not saturate."""
        for name, so, bank in BUILT:
            with self.subTest(core=name):
                var = name.upper() + "_GAIN"
                self.addCleanup(os.environ.pop, var, None)
                levels = {}
                for gain in ("1", "4"):
                    os.environ[var] = gain
                    core = H.Core(so, bank=bank)
                    self.addCleanup(core.close)
                    self.play(core, runs=60)
                    levels[gain] = H.peak(core.audio)
                    self.assertEqual(H.clip_ratio(core.audio), 0.0,
                                     "a single note clips at gain %s" % gain)
                os.environ.pop(var, None)
                self.assertAlmostEqual(levels["4"] / levels["1"], 4.0, delta=0.4,
                                       msg="gain is not linear: %r" % levels)


class TestCoreScreen(CoreCase):
    """The 320x240 framebuffer is the only feedback the device gives."""

    def test_status_field_is_green_with_midi(self):
        for _, core in self.each_core(midi=True):
            self.assertEqual(H.pixel(core.screenshot(), 10, 10), H.GREEN)

    def test_status_field_is_red_without_midi(self):
        for _, core in self.each_core(midi=False):
            self.assertEqual(H.pixel(core.screenshot(), 10, 10), H.RED)

    def test_notes_light_up_their_channel_bars(self):
        for _, core in self.each_core():
            self.assertEqual(H.pixel(core.screenshot(), 10, 215), 0x0000,
                             "bars light up without a note")
            core.note_on(H.LEAD, 69, 110)
            core.note_on(H.DRUM, 36, 110)
            shot = core.screenshot()
            self.assertEqual(H.pixel(shot, 10, 215), H.CHAN_BAR)
            self.assertEqual(H.pixel(shot, 8 + 9 * 19 + 2, 215), H.DRUM_BAR,
                             "channel 10 is not drawn as drums")

    def test_program_bar_grows_with_the_r_button(self):
        def bar_width(shot):
            return sum(1 for x in range(24, 200) if H.pixel(shot, x, 10) == H.WHITE)

        for _, core in self.each_core():
            before = core.screenshot()
            for _ in range(8):
                core.press(H.ID_R)
            self.assertGreater(bar_width(core.screenshot()), bar_width(before),
                               "program bar does not grow")

    def test_screenshot_is_a_valid_png(self):
        for _, core in self.each_core():
            w, h, fb = core.screenshot()
            self.assertEqual((w, h, len(fb)), (320, 240, 320 * 240 * 2))
            with tempfile.TemporaryDirectory() as d:
                path = H.png(os.path.join(d, "s.png"), w, h, fb, scale=1)
                data = Path(path).read_bytes()
            self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertIn(b"IEND", data[-12:])


class TestCoreMidi(CoreCase):
    """The wire format, not just the three messages the harness has helpers for.

    A USB MIDI keyboard mostly sends running status, note-off as velocity 0 and
    realtime bytes in between, so those paths carry the instrument.
    """

    def ready(self, core):
        core.program(H.LEAD, 81)
        core.run(6)
        return core.frames

    def sounding(self, core, start, runs=45):
        core.run(runs)
        return H.rms(H.mono(core.audio, start + H.SR // 50))

    def test_running_status_plays_the_second_note(self):
        for _, core in self.each_core():
            start = self.ready(core)
            core.send(0x90, 60, 100)          # status byte once
            core.send(64, 100)                # running status: data bytes only
            core.send(0x80, 60, 0)            # silence the first one again
            self.assertGreater(self.sounding(core, start), 200.0, "running status note is missing")

    def test_data_bytes_without_a_status_byte_are_ignored(self):
        for _, core in self.each_core():
            start = self.ready(core)
            core.send(64, 100)                # no status has ever been sent
            self.assertLess(self.sounding(core, start), 1.0, "parser invents a note")

    def test_note_on_with_velocity_zero_is_a_note_off(self):
        for _, core in self.each_core():
            start = self.ready(core)
            core.send(0x90, 69, 110)
            loud = self.sounding(core, start)
            off = core.frames
            core.send(0x90, 69, 0)            # the usual note-off from a keyboard
            core.run(45)
            self.assertLess(H.rms(H.mono(core.audio, off + H.SR // 2)), loud * 0.05)

    def test_controller_all_notes_off(self):
        for _, core in self.each_core():
            start = self.ready(core)
            core.send(0x90, 69, 110)
            loud = self.sounding(core, start)
            off = core.frames
            core.send(0xB0, 123, 0)           # CC 123 = all notes off
            core.run(45)
            self.assertLess(H.rms(H.mono(core.audio, off + H.SR // 2)), loud * 0.05)

    def test_pitch_bend_raises_the_pitch(self):
        for _, core in self.each_core():
            self.ready(core)
            core.send(0x90, 69, 110)
            core.run(45)
            flat = H.fundamental(H.mono(core.audio, core.frames - 8192, core.frames - 4096))
            core.send(0xE0, 0x00, 0x60)       # lsb, msb - half of the upward range
            core.run(45)
            bent = H.fundamental(H.mono(core.audio, core.frames - 8192, core.frames - 4096))
            self.assertGreater(bent / flat, 1.03,
                               "pitch bend does nothing (%.1f -> %.1f Hz)" % (flat, bent))

    def test_realtime_bytes_do_not_disturb_the_parser(self):
        """Active sensing arrives constantly, including inside a message."""
        for _, core in self.each_core():
            start = self.ready(core)
            core.send(0x90, 60)               # message cut in half
            core.send(0xFE)                   # active sensing right in the middle
            core.send(100)                    # completes note-on 60
            core.send(0xFE)
            core.send(64, 100)                # running status is still 0x90
            self.assertGreater(self.sounding(core, start), 200.0, "realtime byte swallowed the note")

    def test_sysex_is_skipped_and_ends_running_status(self):
        for _, core in self.each_core():
            start = self.ready(core)
            core.send(0xF0, 0x7E, 0x7F, 0x09, 0x01, 0xF7)   # GM reset
            core.send(69, 110)                # must be ignored: sysex cleared the status
            self.assertLess(self.sounding(core, start), 1.0, "data bytes after sysex were played")
            start = core.frames
            core.send(0x90, 69, 110)          # a full message still works
            self.assertGreater(self.sounding(core, start), 200.0)


@unittest.skipUnless(BUILT, "no built core - run 'make -C cores/adl' first")
class TestBankHandling(unittest.TestCase):
    """retro_load_game with content - adl and opn differ here on purpose."""

    ADL = ROOT / "cores" / "adl" / "adl_libretro.so"
    WOPL = ROOT / "cores" / "adl" / "libADLMIDI" / "fm_banks" / "ail" / "MonopolyDeluxe.wopl"
    OPN = ROOT / "cores" / "opn" / "opn_libretro.so"
    WOPN = BANKS["opn"]

    def play(self, core):
        core.program(H.LEAD, 81)
        core.run(6)
        start = core.frames
        core.note_on(H.LEAD, 69, 110)
        core.run(45)
        return H.rms(H.mono(core.audio, start + H.SR // 50))

    @unittest.skipUnless(ADL.exists() and WOPL.exists(), "adl or its banks are not built")
    def test_adl_loads_a_wopl_bank(self):
        core = H.Core(self.ADL, bank=self.WOPL)
        self.addCleanup(core.close)
        self.assertGreater(self.play(core), 200.0)

    @unittest.skipUnless(ADL.exists(), "adl is not built")
    def test_adl_empty_marker_falls_back_to_the_embedded_bank(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / "embedded.wopl"
            marker.touch()
            core = H.Core(self.ADL, bank=marker)
            self.addCleanup(core.close)
            self.assertGreater(self.play(core), 200.0)

    @unittest.skipUnless(OPN.exists() and WOPN.exists(), "opn or its banks are not built")
    def test_opn_loads_a_wopn_bank(self):
        core = H.Core(self.OPN, bank=self.WOPN)
        self.addCleanup(core.close)
        self.assertGreater(self.play(core), 200.0)

    @unittest.skipUnless(OPN.exists(), "opn is not built")
    def test_opn_without_a_bank_refuses_to_load(self):
        """libOPNMIDI has no embedded bank, so there is nothing to fall back to."""
        with self.assertRaises(SystemExit):
            H.Core(self.OPN)

    def test_a_broken_bank_fails_loudly(self):
        for name, so, _ in BUILT:
            with self.subTest(core=name):
                with tempfile.TemporaryDirectory() as d:
                    broken = Path(d) / ("broken.wop" + name[0])
                    broken.write_bytes(b"not a bank")
                    with self.assertRaises(SystemExit):
                        H.Core(so, bank=broken)


if __name__ == "__main__":
    unittest.main()
