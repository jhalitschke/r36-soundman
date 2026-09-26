#!/usr/bin/env python3
"""Tests for scripts/testtone.py.

The point of generating this content rather than downloading it is that it can
be shipped and re-made at will, so what matters is that the two files really are
what their formats say - a player that rejects them is worth nothing as a test.
The numbers here were read back off the device: gme rendered the VGM at
-6.5 dBFS and FluidSynth the MIDI at -20.1 dBFS.
"""
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "testtone.py"


def make(*args):
    d = Path(tempfile.mkdtemp())
    vgm, midi = d / "t.vgm", d / "t.mid"
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--vgm", str(vgm), "--midi", str(midi), *args],
        capture_output=True, text=True, check=True,
    )
    return vgm, midi, r.stdout


class Vgm(unittest.TestCase):
    def setUp(self):
        self.vgm, _, _ = make()
        self.blob = self.vgm.read_bytes()

    def test_header_says_vgm(self):
        self.assertEqual(self.blob[:4], b"Vgm ")
        self.assertEqual(struct.unpack_from("<I", self.blob, 0x08)[0], 0x150)

    def test_the_eof_offset_points_at_the_end(self):
        """Relative to 0x04, which is the part that is easy to get wrong."""
        eof = struct.unpack_from("<I", self.blob, 0x04)[0]
        self.assertEqual(eof + 4, len(self.blob))

    def test_data_offset_and_end_marker(self):
        data_at = struct.unpack_from("<I", self.blob, 0x34)[0] + 0x34
        self.assertEqual(data_at, 0x40)
        self.assertEqual(self.blob[-1], 0x66, "no end-of-sound-data marker")

    def test_a_chip_is_declared(self):
        """With no chip clock a player has nothing to emulate and bails out."""
        self.assertGreater(struct.unpack_from("<I", self.blob, 0x0C)[0], 0)

    def test_it_actually_writes_to_the_psg(self):
        body = self.blob[0x40:]
        writes = sum(1 for i in range(len(body) - 1) if body[i] == 0x50)
        self.assertGreater(writes, 20, "too few register writes to make a sound")


class Midi(unittest.TestCase):
    def setUp(self):
        _, self.midi, _ = make()
        self.blob = self.midi.read_bytes()

    def test_header_and_single_track(self):
        self.assertEqual(self.blob[:4], b"MThd")
        length, fmt, tracks, div = struct.unpack_from(">IHHH", self.blob, 4)
        self.assertEqual((length, fmt, tracks), (6, 0, 1))
        self.assertGreater(div, 0)

    def test_the_track_length_matches_what_follows(self):
        self.assertEqual(self.blob[14:18], b"MTrk")
        (length,) = struct.unpack_from(">I", self.blob, 18)
        self.assertEqual(22 + length, len(self.blob))

    def test_it_ends_with_end_of_track(self):
        self.assertEqual(self.blob[-3:], b"\xff\x2f\x00")

    def test_there_are_note_ons(self):
        n = sum(1 for b in self.blob[22:] if b == 0x90)
        self.assertGreaterEqual(n, 8, "not enough notes to hear anything")


class Cli(unittest.TestCase):
    def test_it_refuses_to_do_nothing(self):
        r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nothing to write", r.stderr)

    def test_output_is_reproducible(self):
        """Same bytes every time, or the numbers measured on the device mean nothing."""
        a, b, _ = make()
        c, d, _ = make()
        self.assertEqual(a.read_bytes(), c.read_bytes())
        self.assertEqual(b.read_bytes(), d.read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
