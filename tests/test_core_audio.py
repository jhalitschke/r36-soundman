#!/usr/bin/env python3
"""Hörtest ohne Ohren: treibt den gebauten Core und prüft das Audio.

Braucht cores/adl/adl_libretro.so (make -C cores/adl) – fehlt die Datei,
werden die Tests übersprungen (Lint-Job ohne Build).
"""
import importlib.util
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SO = ROOT / "cores" / "adl" / "adl_libretro.so"


def _harness():
    spec = importlib.util.spec_from_file_location("adl_harness", ROOT / "scripts" / "adl_harness.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


H = _harness() if SO.exists() else None


@unittest.skipUnless(SO.exists(), "cores/adl/adl_libretro.so fehlt – erst 'make -C cores/adl'")
class TestCoreAudio(unittest.TestCase):
    def setUp(self):
        os.environ.pop("ADL_GAIN", None)
        self.core = H.Core(SO)
        self.addCleanup(self.core.close)

    def note(self, note=69, programm=81, runs=90):
        """Note spielen, (rms_vorher, rms_klingend, startframe) zurückgeben."""
        self.core.program(H.LEAD, programm)
        self.core.run(6)
        vorher = H.rms(H.mono(self.core.audio))
        start = self.core.frames
        self.core.note_on(H.LEAD, note, 110)
        self.core.run(runs)
        klingend = H.rms(H.mono(self.core.audio, start + H.SR // 50))
        return vorher, klingend, start

    def test_stille_vor_der_ersten_note(self):
        self.core.run(6)
        self.assertLess(H.rms(H.mono(self.core.audio)), 1.0, "Core rauscht ohne Note")

    def test_note_erzeugt_energie(self):
        vorher, klingend, _ = self.note()
        self.assertLess(vorher, 1.0)
        self.assertGreater(klingend, 200.0, "Note-On erzeugt kaum Pegel")

    def test_tonhoehe_stimmt(self):
        for note in (60, 69, 72):
            with self.subTest(note=note):
                core = H.Core(SO)
                self.addCleanup(core.close)
                core.program(H.LEAD, 81)
                core.run(6)
                core.note_on(H.LEAD, note, 110)
                core.run(60)
                start = H.SR // 4
                hz = H.grundfrequenz(H.mono(core.audio, start, start + 4096))
                soll = H.note_hz(note)
                self.assertAlmostEqual(hz / soll, 1.0, delta=0.01,
                                       msg="Note %d: %.1f Hz statt %.1f Hz" % (note, hz, soll))

    def test_note_off_wird_still(self):
        _, klingend, _ = self.note()
        ab = self.core.frames
        self.core.note_off(H.LEAD, 69)
        self.core.run(45)                                  # 0,75 s Ausklang
        nachher = H.rms(H.mono(self.core.audio, ab + H.SR // 2))
        self.assertLess(nachher, klingend * 0.05, "Note-Off klingt nicht aus")

    def test_panic_macht_still(self):
        _, klingend, _ = self.note()
        self.core.taste(H.ID_A)                            # A = adl_panic
        ab = self.core.frames
        self.core.run(30)
        self.assertLess(H.rms(H.mono(self.core.audio, ab + H.SR // 4)), klingend * 0.05,
                        "Panic macht nicht still")

    def test_programmwechsel_per_taste(self):
        self.core.taste(H.ID_R)
        self.core.taste(H.ID_L)
        start = self.core.frames
        self.core.note_on(H.LEAD, 69, 110)
        self.core.run(60)
        self.assertGreater(H.rms(H.mono(self.core.audio, start + H.SR // 50)), 200.0,
                           "nach L/R kommt kein Ton mehr")

    def test_gain_wirkt_und_clippt_nicht(self):
        """ADL_GAIN skaliert linear; eine Einzelnote darf nicht saettigen."""
        pegel = {}
        for gain in ("1", "6"):
            os.environ["ADL_GAIN"] = gain
            core = H.Core(SO)
            self.addCleanup(core.close)
            core.program(H.LEAD, 81)
            core.run(6)
            core.note_on(H.LEAD, 69, 110)
            core.run(60)
            pegel[gain] = H.peak(core.audio)
            self.assertEqual(H.clip_anteil(core.audio), 0.0, "Einzelnote clippt bei Gain %s" % gain)
        os.environ.pop("ADL_GAIN", None)
        self.assertAlmostEqual(pegel["6"] / pegel["1"], 6.0, delta=0.6,
                               msg="Gain nicht linear: %r" % pegel)


if __name__ == "__main__":
    unittest.main()
