#!/usr/bin/env python3
"""es_systems.cfg from the device + es/systems/*.xml -> the merged file on stdout.

Placeholders in the fragments: {{RA}} = the RetroArch invocation up to '-L',
{{CORES}} = the core directory (both derived from the first retroarch command in
the device file).
"""
import sys, re, xml.etree.ElementTree as ET

base, frags = sys.argv[1], sys.argv[2:]
tree = ET.parse(base); root = tree.getroot()
ra, cores = "retroarch", "/roms/cores"
for cmd in root.iter("command"):
    m = re.match(r"(.*?)\s*-L\s+(\S+)", cmd.text or "")
    if m and "retroarch" in m.group(1):
        ra, cores = m.group(1).strip(), m.group(2).rsplit("/", 1)[0]; break
for f in frags:
    txt = open(f).read().replace("{{RA}}", ra).replace("{{CORES}}", cores)
    for sysel in ET.fromstring("<r>%s</r>" % txt).findall("system"):
        name = sysel.findtext("name")
        for old in [s for s in root.findall("system") if s.findtext("name") == name]:
            root.remove(old)
        root.append(sysel)
ET.indent(root)
sys.stdout.write(ET.tostring(root, encoding="unicode") + "\n")
