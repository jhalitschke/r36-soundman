#!/usr/bin/env python3
"""Tests für scripts/es-merge.py und die ES-Fragmente – laufen ohne Gerät.

Prüft, was der Merge garantieren muss: Platzhalter ersetzt, Fragmente drin,
Basissysteme erhalten, zweiter Lauf erzeugt keine Dubletten.
"""
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MERGE = ROOT / "scripts" / "es-merge.py"
FRAGS = sorted((ROOT / "es" / "systems").glob("*.xml"))

# Gerätedatei-Attrappe: ein RetroArch-System (liefert {{RA}}/{{CORES}}) und ein Script-System.
BASE = """<?xml version="1.0"?>
<systemList>
  <system>
    <name>snes</name>
    <fullname>Super Nintendo</fullname>
    <path>/roms/snes</path>
    <extension>.smc .sfc</extension>
    <command>/usr/local/bin/retroarch -L /usr/local/lib/libretro/snes9x_libretro.so %ROM%</command>
    <platform>snes</platform>
    <theme>snes</theme>
  </system>
  <system>
    <name>ports</name>
    <fullname>Ports</fullname>
    <path>/roms/ports</path>
    <extension>.sh</extension>
    <command>bash %ROM%</command>
    <platform>pc</platform>
    <theme>ports</theme>
  </system>
</systemList>
"""

BASE_OHNE_RETROARCH = BASE.replace(
    "/usr/local/bin/retroarch -L /usr/local/lib/libretro/snes9x_libretro.so %ROM%",
    "bash /opt/start_snes.sh %ROM%",
)


def merge(base_xml, frags=FRAGS):
    """es-merge.py mit einer Gerätedatei-Attrappe laufen lassen -> stdout."""
    with tempfile.NamedTemporaryFile("w", suffix=".cfg", delete=False) as f:
        f.write(base_xml)
        base = f.name
    out = subprocess.run(
        [sys.executable, str(MERGE), base, *map(str, frags)],
        capture_output=True, text=True, check=True,
    )
    return out.stdout


def names(xml):
    return [s.findtext("name") for s in ET.fromstring(xml).findall("system")]


class TestMerge(unittest.TestCase):
    def test_platzhalter_werden_ersetzt(self):
        out = merge(BASE)
        self.assertNotIn("{{", out, "Platzhalter nicht ersetzt")
        self.assertIn(
            "/usr/local/bin/retroarch -L /usr/local/lib/libretro/adl_libretro.so",
            out,
            "{{RA}}/{{CORES}} nicht aus dem RetroArch-Command der Gerätedatei abgeleitet",
        )

    def test_fragmente_und_basissysteme_sind_drin(self):
        vorhanden = names(merge(BASE))
        for name in ("snes", "ports"):
            self.assertIn(name, vorhanden, "Basissystem verloren")
        for frag in FRAGS:
            self.assertIn(ET.parse(frag).getroot().findtext("name"), vorhanden)

    def test_zweiter_lauf_erzeugt_keine_dubletten(self):
        einmal = merge(BASE)
        zweimal = merge(einmal)
        self.assertEqual(sorted(names(einmal)), sorted(names(zweimal)))
        self.assertEqual(len(names(zweimal)), len(set(names(zweimal))))

    def test_fallback_ohne_retroarch_command(self):
        out = merge(BASE_OHNE_RETROARCH)
        self.assertIn("retroarch -L /roms/cores/adl_libretro.so", out)

    def test_ausgabe_ist_gueltiges_xml(self):
        root = ET.fromstring(merge(BASE))
        self.assertEqual(root.tag, "systemList")


class TestFragmente(unittest.TestCase):
    def test_fragmente_sind_vollstaendig(self):
        self.assertTrue(FRAGS, "keine ES-Fragmente gefunden")
        for frag in FRAGS:
            with self.subTest(frag=frag.name):
                sysel = ET.parse(frag).getroot()
                self.assertEqual(sysel.tag, "system")
                for tag in ("name", "fullname", "path", "extension", "command", "platform", "theme"):
                    self.assertTrue((sysel.findtext(tag) or "").strip(), "<%s> fehlt" % tag)
                # Solange es keine eigenen Logos gibt: theme="ports" (CLAUDE.md).
                self.assertEqual(sysel.findtext("theme"), "ports")
                self.assertIn("%ROM%", sysel.findtext("command"))
                self.assertEqual(sysel.findtext("path"), "/roms/" + sysel.findtext("name"))

    def test_nur_bekannte_platzhalter(self):
        erlaubt = {"{{RA}}", "{{CORES}}"}
        for frag in FRAGS:
            with self.subTest(frag=frag.name):
                import re
                gefunden = set(re.findall(r"\{\{[^}]*\}\}", frag.read_text()))
                self.assertTrue(gefunden <= erlaubt, "unbekannte Platzhalter: %s" % (gefunden - erlaubt))


if __name__ == "__main__":
    unittest.main()
