#!/usr/bin/env python3
"""Tests for scripts/es-merge.py and the ES fragments - they run without a device.

Checks what the merge has to guarantee: placeholders substituted, fragments
present, base systems kept, a second merge producing no duplicates.
"""
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MERGE = ROOT / "scripts" / "es-merge.py"
FRAGMENTS = sorted((ROOT / "es" / "systems").glob("*.xml"))

# Stand-in for the device file: one RetroArch system (supplies {{RA}}/{{CORES}})
# and one script system.
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

BASE_WITHOUT_RETROARCH = BASE.replace(
    "/usr/local/bin/retroarch -L /usr/local/lib/libretro/snes9x_libretro.so %ROM%",
    "bash /opt/start_snes.sh %ROM%",
)


def merge(base_xml, fragments=FRAGMENTS):
    """Run es-merge.py against a stand-in device file -> stdout."""
    with tempfile.NamedTemporaryFile("w", suffix=".cfg", delete=False) as f:
        f.write(base_xml)
        base = f.name
    out = subprocess.run(
        [sys.executable, str(MERGE), base, *map(str, fragments)],
        capture_output=True, text=True, check=True,
    )
    return out.stdout


def names(xml):
    return [s.findtext("name") for s in ET.fromstring(xml).findall("system")]


class TestMerge(unittest.TestCase):
    def test_placeholders_are_substituted(self):
        out = merge(BASE)
        self.assertNotIn("{{", out, "placeholder left unsubstituted")
        self.assertIn(
            "/usr/local/bin/retroarch -L /usr/local/lib/libretro/adl_libretro.so",
            out,
            "{{RA}}/{{CORES}} not derived from the device file's RetroArch command",
        )

    def test_fragments_and_base_systems_are_present(self):
        present = names(merge(BASE))
        for name in ("snes", "ports"):
            self.assertIn(name, present, "lost a base system")
        for fragment in FRAGMENTS:
            self.assertIn(ET.parse(fragment).getroot().findtext("name"), present)

    def test_second_run_creates_no_duplicates(self):
        once = merge(BASE)
        twice = merge(once)
        self.assertEqual(sorted(names(once)), sorted(names(twice)))
        self.assertEqual(len(names(twice)), len(set(names(twice))))

    def test_fallback_without_retroarch_command(self):
        out = merge(BASE_WITHOUT_RETROARCH)
        self.assertIn("retroarch -L /roms/cores/adl_libretro.so", out)

    def test_output_is_valid_xml(self):
        root = ET.fromstring(merge(BASE))
        self.assertEqual(root.tag, "systemList")


class TestFragments(unittest.TestCase):
    def test_fragments_are_complete(self):
        self.assertTrue(FRAGMENTS, "no ES fragments found")
        for fragment in FRAGMENTS:
            with self.subTest(fragment=fragment.name):
                sysel = ET.parse(fragment).getroot()
                self.assertEqual(sysel.tag, "system")
                for tag in ("name", "fullname", "path", "extension", "command", "platform", "theme"):
                    self.assertTrue((sysel.findtext(tag) or "").strip(), "<%s> missing" % tag)
                # As long as there are no logos of our own: theme="ports" (CLAUDE.md).
                self.assertEqual(sysel.findtext("theme"), "ports")
                self.assertIn("%ROM%", sysel.findtext("command"))
                self.assertEqual(sysel.findtext("path"), "/roms/" + sysel.findtext("name"))

    def test_only_known_placeholders(self):
        allowed = {"{{RA}}", "{{CORES}}"}
        for fragment in FRAGMENTS:
            with self.subTest(fragment=fragment.name):
                found = set(re.findall(r"\{\{[^}]*\}\}", fragment.read_text()))
                self.assertTrue(found <= allowed, "unknown placeholders: %s" % (found - allowed))


if __name__ == "__main__":
    unittest.main()
