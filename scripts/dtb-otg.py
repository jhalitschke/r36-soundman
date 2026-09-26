#!/usr/bin/env python3
"""Report (and optionally fix) the USB2 PHY otg-port in an ArkOS DTB.

RK3326 ArkOS images ship usb@ff300000 (dwc2) with dr_mode="otg" and
status="okay", but the PHY port it refers to - usb2-phy@100/otg-port - with
status="disabled". A compatibility check that only looks at dr_mode therefore
reports the device as fine while the gadget can never be told that a host is
attached. Enabling the port is what makes device mode possible at all.

The patch is done in place and keeps the property length: the kernel reads
"status" with strcmp, so "okay" followed by padding NULs is read as "okay"
while the length stays 9 bytes. No offset in the DTB has to be rewritten,
and the file keeps its size.

    scripts/dtb-otg.py <dtb>...            report only
    scripts/dtb-otg.py --write <dtb>...    enable otg-port, keeping <dtb>.orig
    scripts/dtb-otg.py --write --dr-mode peripheral <dtb>...

--dr-mode is the second lever, for a board whose ID pin is not wired: with
dr_mode="otg" the controller decides its role from the ID pin and stays host
when nothing pulls it low, so it never becomes a device however good the cable
is. "peripheral" forces the gadget role - and gives up host mode on that port,
so an OTG hub will no longer work there. The string is longer than "otg", so
unlike the status patch this rewrites the whole blob.
"""
import struct
import shutil
import sys
from pathlib import Path

FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9
OKAY = b"okay"


def props(blob):
    """Yield (node_path, prop_name, value_offset, length) for every property."""
    magic, _, off_struct, off_strings, _, _, _, _, size_strings, _ = struct.unpack(
        ">10I", blob[:40]
    )
    if magic != 0xD00DFEED:
        raise ValueError("not a DTB (bad magic)")
    strings = blob[off_strings : off_strings + size_strings]
    pos, stack = off_struct, []
    while True:
        (tok,) = struct.unpack(">I", blob[pos : pos + 4])
        pos += 4
        if tok == FDT_BEGIN_NODE:
            end = blob.index(b"\0", pos)
            stack.append(blob[pos:end].decode())
            pos = (end + 4) & ~3
        elif tok == FDT_END_NODE:
            stack.pop()
        elif tok == FDT_PROP:
            length, nameoff = struct.unpack(">II", blob[pos : pos + 8])
            pos += 8
            name = strings[nameoff : strings.index(b"\0", nameoff)].decode()
            yield "/" + "/".join(stack[1:]), name, pos, length
            pos = (pos + length + 3) & ~3
        elif tok == FDT_NOP:
            continue
        elif tok == FDT_END:
            return
        else:
            raise ValueError(f"unknown token {tok} at {pos}")


def find_status(blob, suffix):
    for node, name, off, length in props(blob):
        if name == "status" and node.endswith(suffix):
            return node, off, length
    return None, None, None


def available(value):
    """The kernel's own test: strcmp against "okay"/"ok", so NULs end it."""
    s = value.split(b"\0", 1)[0]
    return s in (b"okay", b"ok")


def blocks(blob):
    """Split a DTB into (header fields, reserve map, struct block, strings)."""
    head = struct.unpack(">10I", blob[:40])
    off_struct, off_strings, off_rsv = head[2], head[3], head[4]
    size_strings, size_struct = head[8], head[9]
    # the reserve map is a list of 16-byte entries ending in an all-zero one
    end = off_rsv
    while blob[end : end + 16] != b"\0" * 16:
        end += 16
    rsv = bytes(blob[off_rsv : end + 16])
    return (
        head,
        rsv,
        bytes(blob[off_struct : off_struct + size_struct]),
        bytes(blob[off_strings : off_strings + size_strings]),
    )


def set_property(blob, node_match, prop, value):
    """Return a new DTB with one property replaced, length change and all.

    node_match is matched as a substring of the node path, and the caller checks
    the returned hit count - naming a node too loosely is caught there rather
    than silently patching several. The value may grow, so the struct block is
    rebuilt and every offset in the header recomputed; an in-place edit only
    works while the length stays equal.
    """
    head, rsv, old_struct, strings = blocks(blob)
    out, pos, stack, hits = bytearray(), 0, [], 0
    while pos < len(old_struct):
        (tok,) = struct.unpack(">I", old_struct[pos : pos + 4])
        if tok == FDT_BEGIN_NODE:
            end = old_struct.index(b"\0", pos + 4)
            stack.append(old_struct[pos + 4 : end].decode())
            nxt = (end + 4) & ~3
            out += old_struct[pos:nxt]
            pos = nxt
        elif tok == FDT_PROP:
            length, nameoff = struct.unpack(">II", old_struct[pos + 4 : pos + 12])
            name = strings[nameoff : strings.index(b"\0", nameoff)].decode()
            body_at = pos + 12
            nxt = (body_at + length + 3) & ~3
            node = "/" + "/".join(stack[1:])
            if name == prop and node_match in node:
                new = value if isinstance(value, bytes) else value.encode() + b"\0"
                out += struct.pack(">III", FDT_PROP, len(new), nameoff)
                out += new + b"\0" * (-len(new) % 4)
                hits += 1
            else:
                out += old_struct[pos:nxt]
            pos = nxt
        else:
            if tok == FDT_END_NODE:
                stack.pop()
            out += old_struct[pos : pos + 4]
            pos += 4

    new_struct = bytes(out)
    off_rsv = 40
    off_struct = off_rsv + len(rsv)
    off_strings = off_struct + len(new_struct)
    total = off_strings + len(strings)
    header = struct.pack(
        ">10I", head[0], total, off_struct, off_strings, off_rsv,
        head[5], head[6], head[7], len(strings), len(new_struct),
    )
    return header + rsv + new_struct + strings, hits


def read_prop(blob, node_match, prop):
    for node, name, off, length in props(blob):
        if name == prop and node_match in node:
            return bytes(blob[off : off + length]).rstrip(b"\0").decode()
    return None


MODES = ("otg", "peripheral", "host")


def main(argv):
    write, dr_mode, files = False, None, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--write":
            write = True
        elif a == "--dr-mode":
            i += 1
            if i >= len(argv):
                print("--dr-mode needs a value")
                return 2
            dr_mode = argv[i]
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        elif a.startswith("-"):
            print(f"unknown option {a}")
            return 2
        else:
            files.append(a)
        i += 1

    if dr_mode is not None and dr_mode not in MODES:
        print(f"--dr-mode must be one of {', '.join(MODES)}")
        return 2
    if not files:
        print(__doc__)
        return 2

    rc = 0
    for name in files:
        path = Path(name)
        blob = bytearray(path.read_bytes())
        try:
            node, off, length = find_status(blob, "/otg-port")
            dr = read_prop(blob, "usb@", "dr_mode")
        except ValueError as exc:
            print(f"{path.name}: {exc}")
            rc = 1
            continue

        if node is None:
            print(f"{path.name}: no otg-port node - nothing to do")
            continue

        value = bytes(blob[off : off + length])
        state = "okay" if available(value) else value.rstrip(b"\0").decode()
        print(f"{path.name}: dr_mode={dr}  {node} status={state}")

        todo = []
        if not available(value):
            todo.append("otg-port")
        if dr_mode is not None and dr != dr_mode:
            todo.append(f"dr_mode {dr} -> {dr_mode}")
        if not todo:
            continue
        if not write:
            print(f"           -> would change: {', '.join(todo)} (needs --write)")
            rc = 1
            continue

        new = blob
        if "otg-port" in todo:
            if length < len(OKAY) + 1:
                print(f"           -> cannot patch status in place (length {length})")
                rc = 1
                continue
            # same length, so no offset in the blob has to move
            new[off : off + length] = OKAY + b"\0" * (length - len(OKAY))
        if dr_mode is not None and dr != dr_mode:
            rebuilt, hits = set_property(bytes(new), "usb@", "dr_mode", dr_mode)
            if hits != 1:
                print(f"           -> expected one dr_mode, found {hits} - not touching it")
                rc = 1
                continue
            new = bytearray(rebuilt)

        orig = path.with_suffix(path.suffix + ".orig")
        if not orig.exists():
            shutil.copy2(path, orig)
            print(f"           -> backup {orig.name}")
        path.write_bytes(new)

        # read the file back rather than trust the write
        check = bytearray(path.read_bytes())
        try:
            _, o2, l2 = find_status(check, "/otg-port")
            dr2 = read_prop(check, "usb@", "dr_mode")
        except ValueError as exc:
            o2, dr2 = None, f"unparseable: {exc}"
        ok = o2 is not None and available(bytes(check[o2 : o2 + l2]))
        if dr_mode is not None:
            ok = ok and dr2 == dr_mode
        if not ok:
            print(f"           -> FAILED (status/dr_mode read back as {dr2}), restoring backup")
            shutil.copy2(orig, path)
            rc = 1
        else:
            print(f"           -> done: otg-port okay, dr_mode={dr2}")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
