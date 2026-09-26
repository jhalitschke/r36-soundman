#!/usr/bin/env python3
"""Write the test content the chip cores and the synth need, from scratch.

    scripts/testtone.py --vgm /tmp/scale.vgm --midi /tmp/scale.mid

Both are generated rather than downloaded, and that is the point. What gme
plays - NSF, VGM, SPC - exists almost exclusively as rips of commercial game
music, so a file that may actually be shipped is far easier to write than to
find: this is a C major scale and a chord, straight out of the format specs,
some two hundred bytes of it. The MIDI file is the same idea for FluidSynth and
for anything driven through the ALSA sequencer.

Neither is music. They exist so that "does sound come out" can be answered
without a licence question and without a keyboard attached.
"""
import argparse
import struct

# A Master System's PSG. The tone divider is clock / (32 * frequency), and the
# scale below is the one an ear recognises as going up.
SN76489_CLOCK = 3579545
VGM_RATE = 44100
SCALE = (261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 493.88, 523.25)
CHORD = (261.63, 329.63, 392.00)


def _psg_latch(channel, is_volume, value):
    """Latch byte 1ccTdddd, plus the second byte a tone's top six bits need."""
    out = bytes([0x80 | (channel << 5) | (0x10 if is_volume else 0) | (value & 0x0F)])
    if not is_volume:
        out += bytes([(value >> 4) & 0x3F])
    return out


def _psg_tone(freq):
    return max(1, min(0x3FF, round(SN76489_CLOCK / (32 * freq))))


def write_vgm(path):
    body = bytearray()

    def reg(byte):
        body.extend(b"\x50" + bytes([byte]))

    def wait(seconds):
        body.extend(struct.pack("<BH", 0x61, int(VGM_RATE * seconds)))

    for channel in range(4):                       # start silent, including noise
        for b in _psg_latch(channel, True, 15):
            reg(b)
    for freq in SCALE:
        for b in _psg_latch(0, False, _psg_tone(freq)):
            reg(b)
        for b in _psg_latch(0, True, 0):           # attenuation 0 is full volume
            reg(b)
        wait(0.22)
        for b in _psg_latch(0, True, 15):
            reg(b)
        wait(0.03)
    for channel, freq in enumerate(CHORD):
        for b in _psg_latch(channel, False, _psg_tone(freq)):
            reg(b)
        for b in _psg_latch(channel, True, 2):
            reg(b)
    wait(1.0)
    for channel in range(3):
        for b in _psg_latch(channel, True, 15):
            reg(b)
    wait(0.1)
    body.append(0x66)                              # end of sound data

    head = bytearray(0x40)                         # VGM 1.50: data starts at 0x40
    head[0x00:0x04] = b"Vgm "
    struct.pack_into("<I", head, 0x08, 0x00000150)
    struct.pack_into("<I", head, 0x0C, SN76489_CLOCK)
    struct.pack_into("<I", head, 0x24, 60)
    struct.pack_into("<I", head, 0x18, int(VGM_RATE * 3.1))
    struct.pack_into("<I", head, 0x34, 0x0C)       # relative to 0x34
    struct.pack_into("<I", head, 0x04, 0x40 + len(body) - 4)   # EOF, relative to 0x04
    with open(path, "wb") as fh:
        fh.write(bytes(head) + bytes(body))
    return 0x40 + len(body)


def _vlq(n):
    """MIDI's variable-length quantity, high bit set on all but the last byte."""
    out = bytes([n & 0x7F])
    n >>= 7
    while n:
        out = bytes([(n & 0x7F) | 0x80]) + out
        n >>= 7
    return out


def write_midi(path, ticks=480):
    NOTES = (60, 62, 64, 65, 67, 69, 71, 72)
    ev = bytearray()
    ev += b"\x00" + bytes([0xC0, 0])               # acoustic grand, so any GM bank has it
    for chord in ([60, 64, 67], [62, 65, 69]):
        for note in chord:
            ev += b"\x00" + bytes([0x90, note, 100])
        ev += _vlq(ticks) + bytes([0x80, chord[0], 0])
        for note in chord[1:]:
            ev += b"\x00" + bytes([0x80, note, 0])
    for note in NOTES:
        ev += b"\x00" + bytes([0x90, note, 100])
        ev += _vlq(ticks // 2) + bytes([0x80, note, 0])
    ev += _vlq(ticks) + b"\xFF\x2F\x00"            # end of track

    head = b"MThd" + struct.pack(">IHHH", 6, 0, 1, ticks)
    track = b"MTrk" + struct.pack(">I", len(ev)) + bytes(ev)
    with open(path, "wb") as fh:
        fh.write(head + track)
    return len(head) + len(track)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--vgm", help="write a SN76489 scale here (for gme)")
    ap.add_argument("--midi", help="write a MIDI scale here (for fluidsynth)")
    args = ap.parse_args()
    if not args.vgm and not args.midi:
        ap.error("nothing to write - pass --vgm and/or --midi")
    if args.vgm:
        print(f"{args.vgm}: {write_vgm(args.vgm)} bytes")
    if args.midi:
        print(f"{args.midi}: {write_midi(args.midi)} bytes")


if __name__ == "__main__":
    main()
