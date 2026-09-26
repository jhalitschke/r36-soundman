#!/usr/bin/env python3
"""Tests for scripts/dtb-otg.py without a card in the reader.

The patch is a byte edit inside a binary the device boots from, so the things
worth asserting are that it stays the same length, that it only ever touches
the otg-port node, and that a file it cannot handle is left alone. The DTB the
tests run against is built here rather than checked in - a fixture copied from
a device would be an undocumented blob nobody could regenerate.
"""
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "dtb-otg.py"

FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_END = 1, 2, 3, 9
MAGIC = 0xD00DFEED


def pad4(b):
    return b + b"\0" * (-len(b) % 4)


class Builder:
    """Just enough DTB writer to exercise the patch."""

    def __init__(self):
        self.struct = bytearray()
        self.strings = bytearray()

    def _strid(self, name):
        key = name.encode() + b"\0"
        at = self.strings.find(key)
        if at == -1:
            at = len(self.strings)
            self.strings += key
        return at

    def begin(self, name):
        self.struct += struct.pack(">I", FDT_BEGIN_NODE) + pad4(name.encode() + b"\0")
        return self

    def end(self):
        self.struct += struct.pack(">I", FDT_END_NODE)
        return self

    def prop(self, name, value):
        if isinstance(value, str):
            value = value.encode() + b"\0"
        self.struct += struct.pack(">III", FDT_PROP, len(value), self._strid(name))
        self.struct += pad4(value)
        return self

    def build(self):
        body = bytes(self.struct) + struct.pack(">I", FDT_END)
        off_rsv = 40
        off_struct = off_rsv + 16
        off_strings = off_struct + len(body)
        total = off_strings + len(self.strings)
        header = struct.pack(
            ">10I", MAGIC, total, off_struct, off_strings, off_rsv,
            17, 16, 0, len(self.strings), len(body),
        )
        return header + b"\0" * 16 + body + bytes(self.strings)


def make_dtb(otg_status="disabled", dr_mode="otg"):
    b = Builder().begin("")
    b.begin("syscon@ff2c0000").begin("usb2-phy@100").prop("status", "okay")
    b.begin("otg-port").prop("status", otg_status).prop("phandle", struct.pack(">I", 0x8B)).end()
    b.begin("host-port").prop("status", "okay").end()
    b.end().end()
    b.begin("usb@ff300000").prop("dr_mode", dr_mode).prop("status", "okay")
    b.prop("phys", struct.pack(">I", 0x8B)).end()
    return b.end().build()


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True
    )


def statuses(path):
    """All status properties, by node name, from an independent walk of the blob."""
    blob = Path(path).read_bytes()
    _, _, off_struct, off_strings, _, _, _, _, size_strings, _ = struct.unpack(">10I", blob[:40])
    strings = blob[off_strings:off_strings + size_strings]
    pos, stack, found = off_struct, [], {}
    while True:
        (tok,) = struct.unpack(">I", blob[pos:pos + 4])
        pos += 4
        if tok == FDT_BEGIN_NODE:
            end = blob.index(b"\0", pos)
            stack.append(blob[pos:end].decode())
            pos = (end + 4) & ~3
        elif tok == FDT_END_NODE:
            stack.pop()
        elif tok == FDT_PROP:
            length, nameoff = struct.unpack(">II", blob[pos:pos + 8])
            pos += 8
            name = strings[nameoff:strings.index(b"\0", nameoff)].decode()
            value = blob[pos:pos + length]
            pos = (pos + length + 3) & ~3
            if name == "status":
                found[stack[-1]] = value
        elif tok == FDT_END:
            return found


def allprops(path):
    """Every (node, prop, value) in file order - to prove nothing else moved."""
    blob = Path(path).read_bytes()
    _, _, off_struct, off_strings, _, _, _, _, size_strings, _ = struct.unpack(">10I", blob[:40])
    strings = blob[off_strings:off_strings + size_strings]
    pos, stack, out = off_struct, [], []
    while True:
        (tok,) = struct.unpack(">I", blob[pos:pos + 4])
        pos += 4
        if tok == FDT_BEGIN_NODE:
            end = blob.index(b"\0", pos)
            stack.append(blob[pos:end].decode())
            pos = (end + 4) & ~3
        elif tok == FDT_END_NODE:
            stack.pop()
        elif tok == FDT_PROP:
            length, nameoff = struct.unpack(">II", blob[pos:pos + 8])
            pos += 8
            value = blob[pos:pos + length]
            pos = (pos + length + 3) & ~3
            name = strings[nameoff:strings.index(b"\0", nameoff)].decode()
            out.append(("/" + "/".join(stack[1:]), name, value))
        elif tok == FDT_END:
            return out


class DtbOtg(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.dtb = self.tmp / "rk3326-r36sPlus-linux.dtb"
        self.dtb.write_bytes(make_dtb())

    def test_report_only_leaves_the_file_alone(self):
        before = self.dtb.read_bytes()
        r = run(str(self.dtb))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("status=disabled", r.stdout)
        self.assertEqual(self.dtb.read_bytes(), before)
        self.assertFalse((self.tmp / "rk3326-r36sPlus-linux.dtb.orig").exists())

    def test_write_enables_the_port_without_changing_the_size(self):
        before = self.dtb.read_bytes()
        r = run("--write", str(self.dtb))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        after = self.dtb.read_bytes()
        self.assertEqual(len(after), len(before))
        # the kernel compares with strcmp, so NUL padding keeps the length
        self.assertEqual(statuses(self.dtb)["otg-port"], b"okay\0\0\0\0\0")
        self.assertEqual(sum(a != b for a, b in zip(before, after)), 8)

    def test_write_keeps_a_backup_and_is_idempotent(self):
        orig = self.tmp / "rk3326-r36sPlus-linux.dtb.orig"
        before = self.dtb.read_bytes()
        run("--write", str(self.dtb))
        self.assertEqual(orig.read_bytes(), before)
        # a second run must not overwrite the backup with the patched file
        r = run("--write", str(self.dtb))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(orig.read_bytes(), before)

    def test_an_already_enabled_port_is_not_touched(self):
        dtb = self.tmp / "ok.dtb"
        dtb.write_bytes(make_dtb(otg_status="okay"))
        before = dtb.read_bytes()
        r = run("--write", str(dtb))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("status=okay", r.stdout)
        self.assertEqual(dtb.read_bytes(), before)
        self.assertFalse((self.tmp / "ok.dtb.orig").exists())

    def test_only_the_otg_port_status_changes(self):
        """Every other node keeps the status it had - host-port above all."""
        before = statuses(self.dtb)
        run("--write", str(self.dtb))
        after = statuses(self.dtb)
        self.assertEqual(set(before), set(after))
        changed = {k for k in before if before[k] != after[k]}
        self.assertEqual(changed, {"otg-port"})
        self.assertEqual(after["host-port"], b"okay\0")

    def test_a_file_that_is_not_a_dtb_is_refused(self):
        junk = self.tmp / "Image"
        junk.write_bytes(b"\x7fELF" + b"\0" * 200)
        before = junk.read_bytes()
        r = run("--write", str(junk))
        self.assertEqual(r.returncode, 1)
        self.assertIn("not a DTB", r.stdout)
        self.assertEqual(junk.read_bytes(), before)


class DrMode(unittest.TestCase):
    """--dr-mode rewrites the blob, because "peripheral" is longer than "otg"."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.dtb = self.tmp / "board.dtb"
        self.dtb.write_bytes(make_dtb())

    def test_peripheral_changes_only_the_two_intended_properties(self):
        before = allprops(self.dtb)
        r = run("--write", "--dr-mode", "peripheral", str(self.dtb))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        after = allprops(self.dtb)
        self.assertEqual([(n, p) for n, p, _ in before], [(n, p) for n, p, _ in after])
        changed = {(n, p) for (n, p, x), (_, _, y) in zip(before, after) if x != y}
        self.assertEqual(
            changed, {("/syscon@ff2c0000/usb2-phy@100/otg-port", "status"),
                      ("/usb@ff300000", "dr_mode")}
        )

    def test_the_header_matches_the_grown_file(self):
        run("--write", "--dr-mode", "peripheral", str(self.dtb))
        blob = self.dtb.read_bytes()
        head = struct.unpack(">10I", blob[:40])
        self.assertEqual(head[1], len(blob))                    # totalsize
        self.assertEqual(head[3], head[2] + head[9])            # strings after struct
        self.assertEqual(head[3] + head[8], len(blob))          # strings end the file
        self.assertEqual(head[0], MAGIC)

    def test_it_round_trips_back_to_otg(self):
        before = allprops(self.dtb)
        run("--write", "--dr-mode", "peripheral", str(self.dtb))
        r = run("--write", "--dr-mode", "otg", str(self.dtb))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        after = dict(((n, p), v) for n, p, v in allprops(self.dtb))
        self.assertEqual(after[("/usb@ff300000", "dr_mode")], b"otg\0")
        # only the otg-port status stays changed from the first run
        changed = {(n, p) for n, p, v in before if after[(n, p)] != v}
        self.assertEqual(changed, {("/syscon@ff2c0000/usb2-phy@100/otg-port", "status")})

    def test_a_mode_that_is_not_a_mode_is_refused(self):
        before = self.dtb.read_bytes()
        r = run("--write", "--dr-mode", "gadget", str(self.dtb))
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.dtb.read_bytes(), before)

    def test_reporting_names_both_pending_changes(self):
        before = self.dtb.read_bytes()
        r = run("--dr-mode", "peripheral", str(self.dtb))
        self.assertEqual(r.returncode, 1)
        self.assertIn("otg-port", r.stdout)
        self.assertIn("dr_mode otg -> peripheral", r.stdout)
        self.assertEqual(self.dtb.read_bytes(), before)

    def test_an_ambiguous_dr_mode_is_left_alone(self):
        """Two usb nodes with dr_mode: refuse rather than guess which is dwc2."""
        b = Builder().begin("")
        b.begin("syscon@ff2c0000").begin("usb2-phy@100").prop("status", "okay")
        b.begin("otg-port").prop("status", "disabled").end()
        b.end().end()
        b.begin("usb@ff300000").prop("dr_mode", "otg").end()
        b.begin("usb@ff400000").prop("dr_mode", "otg").end()
        two = self.tmp / "two.dtb"
        two.write_bytes(b.end().build())
        before = two.read_bytes()
        r = run("--write", "--dr-mode", "peripheral", str(two))
        self.assertEqual(r.returncode, 1)
        self.assertIn("found 2", r.stdout)
        self.assertEqual(two.read_bytes(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
