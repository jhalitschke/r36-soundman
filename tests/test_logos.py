#!/usr/bin/env python3
"""The generated system logos - no device and no built core needed.

A missing glyph renders as a gap rather than failing, and an edit to the
generator that nobody re-ran leaves stale files in the tree. Both are caught
here.
"""
import importlib.util
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / "es" / "theme" / "make-logos.py"
LOGOS = ROOT / "es" / "theme" / "logos"


def generator():
    spec = importlib.util.spec_from_file_location("make_logos", GEN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = generator()


class TestLogos(unittest.TestCase):
    def test_every_character_has_a_glyph(self):
        for name, title, subtitle, _ in M.SYSTEMS:
            with self.subTest(system=name):
                missing = {c for c in (title + subtitle).upper() if c not in M.FONT}
                self.assertFalse(missing, "no glyph for %s - it would render as a gap" % sorted(missing))

    def test_icons_are_well_formed(self):
        for name, icon in M.ICONS.items():
            with self.subTest(system=name):
                self.assertEqual(len(icon), 16, "icon is not 16 rows")
                for row in icon:
                    self.assertEqual(len(row), 16, "icon row is not 16 columns")
                    self.assertFalse(set(row) - set(".#o"), "unknown pixel in %r" % row)

    def test_every_es_system_has_a_logo(self):
        systems = {ET.parse(f).getroot().findtext("name") for f in (ROOT / "es" / "systems").glob("*.xml")}
        drawn = {name for name, _, _, _ in M.SYSTEMS}
        self.assertFalse(systems - drawn, "ES systems without a logo: %s" % sorted(systems - drawn))

    def test_committed_files_match_the_generator(self):
        """Catches an edited generator that nobody re-ran."""
        with tempfile.TemporaryDirectory() as d:
            for name, title, subtitle, accent in M.SYSTEMS:
                width, height, rects = M.build(name, title, subtitle, accent)
                svg, png = Path(d) / (name + ".svg"), Path(d) / (name + ".png")
                M.write_svg(svg, width, height, rects)
                M.write_png(png, width, height, rects)
                for fresh in (svg, png):
                    committed = LOGOS / fresh.name
                    with self.subTest(file=fresh.name):
                        self.assertTrue(committed.exists(), "logo is missing from the repo")
                        self.assertEqual(committed.read_bytes(), fresh.read_bytes(),
                                         "stale file - run python3 es/theme/make-logos.py")


if __name__ == "__main__":
    unittest.main()
