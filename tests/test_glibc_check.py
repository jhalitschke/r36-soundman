#!/usr/bin/env python3
"""Tests for scripts/glibc-check.py.

The check exists because the cores are cross-built in a container whose Ubuntu
is newer than the device's, and what matters is not the release but whether the
linker bound a symbol version the device cannot provide. These tests run against
whatever ELF the interpreter itself is, so they say nothing about a particular
glibc - only that the reading and the comparison are right.
"""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "glibc-check.py"
SELF = Path(sys.executable)


def is_elf(p):
    try:
        return p.read_bytes()[:4] == b"\x7fELF"
    except OSError:
        return False


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True
    )


@unittest.skipUnless(is_elf(SELF), "needs an ELF to look at")
class GlibcCheck(unittest.TestCase):
    def test_a_generous_limit_passes(self):
        r = run("--max", "99.99", str(SELF))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("libc.so.6", r.stdout)

    def test_an_impossible_limit_fails_and_names_the_symbols(self):
        r = run("--max", "GLIBC_2.0", str(SELF))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("device has GLIBC_2.0", r.stdout)
        self.assertIn("libc.so.6 needs GLIBC_", r.stdout)

    def test_a_bare_number_still_means_glibc(self):
        """The first spelling was --max 2.30; keep it working."""
        self.assertEqual(run("--max", "2.0", str(SELF)).returncode, 1)
        self.assertEqual(run("--max", "99.99", str(SELF)).returncode, 0)

    def test_the_cxx_runtime_is_checked_too(self):
        """A core links libstdc++, so its versions matter as much as libc's."""
        r = run("--max", "GLIBCXX_1.0", "--max", "GLIBC_99.0",
                "--max", "CXXABI_99.0", str(SELF))
        if "libstdc++" not in r.stdout:
            self.skipTest("this binary does not link libstdc++")
        self.assertEqual(r.returncode, 1)
        self.assertIn("device has GLIBCXX_1.0", r.stdout)

    def test_an_unreadable_limit_is_refused(self):
        r = run("--max", "not-a-version", str(SELF))
        self.assertEqual(r.returncode, 2)

    def test_versions_agree_with_readelf(self):
        """If binutils is here, the parse has an independent witness."""
        try:
            out = subprocess.run(
                ["readelf", "-V", str(SELF)], capture_output=True, text=True, check=True
            ).stdout
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("no readelf")
        wanted = out.split("Version needs", 1)
        if len(wanted) < 2:
            self.skipTest("this binary has no version needs")
        theirs = sorted({
            w.split("Name: ", 1)[1].split()[0]
            for w in wanted[1].split("\n") if "Name: " in w
        })
        mine = run("--max", "99.99", str(SELF)).stdout.splitlines()[1:]
        ours = sorted({v for line in mine for v in line.split()[1:]})
        self.assertEqual(theirs, ours)

    def test_a_file_that_is_not_an_elf_is_reported_not_crashed(self):
        with tempfile.TemporaryDirectory() as d:
            junk = Path(d) / "notelf.so"
            junk.write_bytes(b"this is not an ELF file" * 10)
            r = run("--max", "2.30", str(junk))
            self.assertEqual(r.returncode, 1)
            self.assertIn("cannot read", r.stdout)

    def test_the_limit_comparison_is_numeric_not_lexical(self):
        """2.9 < 2.30 as versions, though not as strings."""
        spec = importlib.util.spec_from_file_location("glibc_check", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertLess(mod.as_tuple("2.9"), mod.as_tuple("2.30"))
        self.assertLess(mod.as_tuple("2.2.5"), mod.as_tuple("2.3"))
        self.assertGreater(mod.as_tuple("2.34"), mod.as_tuple("2.30"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
