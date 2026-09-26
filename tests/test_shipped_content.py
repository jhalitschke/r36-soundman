#!/usr/bin/env python3
"""What the repo ships to /roms, and whether it may be shipped at all.

opn has no embedded bank and refuses to start without one, so a bank travels
with the repo. Most WOPN banks are lifted from commercial games and say nothing
about licensing; this checks that the one being shipped does say something, and
that the statement travels with it.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANK = ROOT / "cores" / "opn" / "Doom32x-fixx.wopn"
README = ROOT / "cores" / "opn" / "Doom32x-fixx-readme.txt"


class ShippedBank(unittest.TestCase):
    def test_the_bank_is_there_and_is_a_wopn(self):
        self.assertTrue(BANK.exists(), "opn ships no bank, so it cannot start")
        self.assertTrue(
            BANK.read_bytes().startswith(b"WOPN2-B2NK"),
            "not a WOPN file - libOPNMIDI would refuse it",
        )

    def test_its_licence_travels_with_it(self):
        self.assertTrue(README.exists(), "a bank without its readme is a bank without a licence")
        text = README.read_text(errors="replace").lower()
        self.assertIn("mit", text)
        self.assertIn("freely", text)

    def test_deploy_puts_it_on_the_device(self):
        """A bank nobody copies is a bank opn still cannot start from."""
        deploy = (ROOT / "scripts" / "deploy.sh").read_text()
        self.assertIn(BANK.name, deploy)
        self.assertIn(README.name, deploy)
        # and it must not clobber a bank the user put there
        self.assertIn("[ -e /roms/opn/%s ]" % BANK.name, deploy)


if __name__ == "__main__":
    unittest.main(verbosity=2)
