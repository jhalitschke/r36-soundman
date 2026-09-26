#!/usr/bin/env python3
"""es_systems.cfg from the device + es/systems/*.xml -> the merged file on stdout.

    es-merge.py <device es_systems.cfg> <fragment.xml>... [--cores <dir>]

Placeholders in the fragments:
    {{RA}}     the RetroArch invocation up to '-L'
    {{CORES}}  the core directory
    {{TAIL}}   whatever the device's own command carries after the core path
               (--config, --appendconfig, %ROM%) - ArkOS commands rely on it

RA and TAIL are derived from the device file; a 64-bit retroarch command is
preferred over retroarch32, whose core directory holds 32-bit cores our arm64
builds cannot go into. --cores overrides the directory, which is how deploy.sh
passes the libretro_directory it actually copied into, instead of letting this
script guess a second time.
"""
import sys, re, xml.etree.ElementTree as ET

args = sys.argv[1:]
cores_override = None
if "--cores" in args:
    i = args.index("--cores")
    cores_override = args[i + 1]
    del args[i:i + 2]
base, frags = args[0], args[1:]

tree = ET.parse(base); root = tree.getroot()
ra, cores, tail = "retroarch", "/roms/cores", "%ROM%"
best = None
for cmd in root.iter("command"):
    m = re.match(r"(.*?)\s*-L\s+(\S+)\s*(.*)", (cmd.text or "").strip())
    if not m or "retroarch" not in m.group(1):
        continue
    is32 = "retroarch32" in m.group(1) or "retroarch32" in m.group(2)
    if best is None or (best[0] and not is32):     # prefer the 64-bit command
        best = (is32, m)
    if not is32:
        break
if best:
    m = best[1]
    ra = m.group(1).strip()
    core_path = m.group(2)
    cores = core_path.rsplit("/", 1)[0] if "/" in core_path else "."
    tail = m.group(3).strip() or "%ROM%"
if cores_override:
    cores = cores_override.rstrip("/")

for f in frags:
    txt = (open(f).read().replace("{{RA}}", ra)
           .replace("{{CORES}}", cores).replace("{{TAIL}}", tail))
    for sysel in ET.fromstring("<r>%s</r>" % txt).findall("system"):
        name = sysel.findtext("name")
        for old in [s for s in root.findall("system") if s.findtext("name") == name]:
            root.remove(old)
        root.append(sysel)
ET.indent(root)
sys.stdout.write('<?xml version="1.0"?>\n' + ET.tostring(root, encoding="unicode") + "\n")
