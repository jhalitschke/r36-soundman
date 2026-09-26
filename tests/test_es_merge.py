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

# What ArkOS actually ships: a command with a bare ampersand, which ES reads
# without complaint and which is not well-formed XML. Anything that parses the
# device file strictly falls over on the whole thing.
BASE_WITH_BARE_AMPERSAND = BASE.replace(
    "<command>bash %ROM%</command>",
    "<command>sudo chmod 666 /dev/tty1; %ROM% 2>&1 > /dev/tty1</command>",
)

BASE_WITHOUT_RETROARCH = BASE.replace(
    "/usr/local/bin/retroarch -L /usr/local/lib/libretro/snes9x_libretro.so %ROM%",
    "bash /opt/start_snes.sh %ROM%",
)


def merge(base_xml, fragments=FRAGMENTS, extra=()):
    """Run es-merge.py against a stand-in device file -> stdout."""
    with tempfile.TemporaryDirectory() as d:
        base = Path(d) / "es_systems.cfg"
        base.write_text(base_xml)
        out = subprocess.run(
            [sys.executable, str(MERGE), str(base), *map(str, fragments), *extra],
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

    def test_a_bare_ampersand_in_the_device_file_is_survived(self):
        """ArkOS ships "2>&1" in a command; ES shrugs, a strict parser does not."""
        out = merge(BASE_WITH_BARE_AMPERSAND)
        self.assertIn("adlib", names(out))
        # and what comes back out is valid XML, with the ampersand as an entity
        root = ET.fromstring(out)
        cmds = [c.text for c in root.iter("command")]
        self.assertTrue(
            any("2>&1" in c for c in cmds),
            "the device's own command was lost or mangled",
        )

    def test_output_is_valid_xml(self):
        root = ET.fromstring(merge(BASE))
        self.assertEqual(root.tag, "systemList")


class TestRetroArchProbe(unittest.TestCase):
    """The device file decides {{RA}}/{{CORES}}/{{TAIL}} - ArkOS has two RetroArchs."""

    RA32 = BASE.replace(
        "/usr/local/bin/retroarch -L /usr/local/lib/libretro/snes9x_libretro.so %ROM%",
        "/usr/local/bin/retroarch32 -L /usr/local/lib/libretro32/snes9x_libretro.so "
        "--config /home/ark/.config/retroarch32/retroarch.cfg %ROM%")

    BOTH = RA32.replace("</systemList>", """  <system>
    <name>psx</name>
    <fullname>PlayStation</fullname>
    <path>/roms/psx</path>
    <extension>.cue</extension>
    <command>/usr/local/bin/retroarch -L /usr/local/lib/libretro/pcsx_libretro.so --config /home/ark/.config/retroarch/retroarch.cfg %ROM%</command>
    <platform>psx</platform>
    <theme>psx</theme>
  </system>
</systemList>""")

    def test_trailing_arguments_are_kept(self):
        out = merge(self.RA32.replace("retroarch32", "retroarch").replace("libretro32", "libretro"))
        self.assertIn("--config /home/ark/.config/retroarch/retroarch.cfg %ROM%", out,
                      "the device command's tail was dropped")

    def test_the_64_bit_retroarch_wins(self):
        out = merge(self.BOTH)
        self.assertIn("/usr/local/bin/retroarch -L /usr/local/lib/libretro/adl_libretro.so", out)
        self.assertNotIn("retroarch32 -L", out.split("<name>adlib</name>")[1][:400])

    def test_cores_override_beats_the_device_file(self):
        out = merge(self.BOTH, extra=["--cores", "/home/ark/.config/retroarch/cores"])
        self.assertIn("-L /home/ark/.config/retroarch/cores/adl_libretro.so", out)

    def test_output_starts_with_an_xml_declaration(self):
        self.assertTrue(merge(BASE).startswith("<?xml"))


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
                # Either the fragment names the ROM itself, or it inherits the
                # device command's tail, which carries %ROM%.
                command = sysel.findtext("command")
                self.assertTrue("%ROM%" in command or "{{TAIL}}" in command,
                                "command passes no ROM: %s" % command)
                self.assertEqual(sysel.findtext("path"), "/roms/" + sysel.findtext("name"))

    def test_only_known_placeholders(self):
        allowed = {"{{RA}}", "{{CORES}}", "{{TAIL}}"}
        for fragment in FRAGMENTS:
            with self.subTest(fragment=fragment.name):
                found = set(re.findall(r"\{\{[^}]*\}\}", fragment.read_text()))
                self.assertTrue(found <= allowed, "unknown placeholders: %s" % (found - allowed))


if __name__ == "__main__":
    unittest.main()
