#!/usr/bin/env python3
"""Generate the system logos for the ES carousel: es/theme/logos/<system>.{svg,png}

Everything is drawn from pixel grids, so the SVG (rectangles, no text element -
EmulationStation renders SVG with nanosvg, which does not draw <text>) and the
PNG come out of the same description and cannot drift apart. The pixel look is
also the point: at ~300 px on a 3.5" screen, thin vector strokes disappear.

    python3 es/theme/make-logos.py
"""
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent / "logos"

# 5x7 pixel font, enough for the wordmarks.
FONT = {
    "A": ".###.|#...#|#...#|#####|#...#|#...#|#...#",
    "B": "####.|#...#|#...#|####.|#...#|#...#|####.",
    "C": ".###.|#...#|#....|#....|#....|#...#|.###.",
    "D": "####.|#...#|#...#|#...#|#...#|#...#|####.",
    "E": "#####|#....|#....|####.|#....|#....|#####",
    "F": "#####|#....|#....|####.|#....|#....|#....",
    "G": ".###.|#...#|#....|#.###|#...#|#...#|.###.",
    "H": "#...#|#...#|#...#|#####|#...#|#...#|#...#",
    "I": "#####|..#..|..#..|..#..|..#..|..#..|#####",
    "J": "..###|...#.|...#.|...#.|...#.|#..#.|.##..",
    "K": "#...#|#..#.|#.#..|##...|#.#..|#..#.|#...#",
    "L": "#....|#....|#....|#....|#....|#....|#####",
    "M": "#...#|##.##|#.#.#|#...#|#...#|#...#|#...#",
    "N": "#...#|##..#|#.#.#|#..##|#...#|#...#|#...#",
    "O": ".###.|#...#|#...#|#...#|#...#|#...#|.###.",
    "P": "####.|#...#|#...#|####.|#....|#....|#....",
    "Q": ".###.|#...#|#...#|#...#|#.#.#|#..#.|.##.#",
    "R": "####.|#...#|#...#|####.|#.#..|#..#.|#...#",
    "S": ".####|#....|#....|.###.|....#|....#|####.",
    "T": "#####|..#..|..#..|..#..|..#..|..#..|..#..",
    "U": "#...#|#...#|#...#|#...#|#...#|#...#|.###.",
    "V": "#...#|#...#|#...#|#...#|#...#|.#.#.|..#..",
    "W": "#...#|#...#|#...#|#.#.#|#.#.#|##.##|#...#",
    "X": "#...#|#...#|.#.#.|..#..|.#.#.|#...#|#...#",
    "Y": "#...#|#...#|.#.#.|..#..|..#..|..#..|..#..",
    "Z": "#####|....#|...#.|..#..|.#...|#....|#####",
    "0": ".###.|#...#|#..##|#.#.#|##..#|#...#|.###.",
    "2": ".###.|#...#|....#|...#.|..#..|.#...|#####",
    "3": "#####|...#.|..#..|...#.|....#|#...#|.###.",
    "8": ".###.|#...#|#...#|.###.|#...#|#...#|.###.",
    " ": ".....|.....|.....|.....|.....|.....|.....",
    "-": ".....|.....|.....|#####|.....|.....|.....",
}

# Icons, 16 wide. '#' = accent colour, 'o' = light, '.' = transparent.
ICONS = {
    # ADSR envelope over a ground line: attack, decay, sustain, release.
    "synth": [
        "................",
        "................",
        "....#...........",
        "...###..........",
        "...#.#..........",
        "...#.##.........",
        "..##..#.........",
        "..#...########..",
        "..#..........#..",
        ".##..........##.",
        ".#............#.",
        ".#............#.",
        "##............##",
        "#..............#",
        "#..............#",
        "oooooooooooooooo",
    ],
    # Square wave, two cycles.
    "chiptune": [
        "................",
        "................",
        "................",
        "................",
        "####...#####....",
        "...#...#...#....",
        "...#...#...#....",
        "...#...#...#....",
        "...#...#...#....",
        "...#...#...#....",
        "...#...#...#....",
        "...#####...#####",
        "................",
        "................",
        "................",
        "................",
    ],
    # A DIP sound chip with a sine inside - AdLib is an OPL3 chip.
    "adlib": [
        ".....o..o..o....",
        ".....o..o..o....",
        "..oooooooooooo..",
        "..o..........o..",
        "..o..........o..",
        "..o..........o..",
        "..o...#......o..",
        "..o..#.#.....o..",
        "..o.#...#....o..",
        "..o......#.#.o..",
        "..o.......#..o..",
        "..o..........o..",
        "..o..........o..",
        "..oooooooooooo..",
        ".....o..o..o....",
        ".....o..o..o....",
    ],
    # Tracker pattern: four columns of rows, the playhead row highlighted.
    "lgpt": [
        "................",
        "ooo.ooo.ooo.ooo.",
        "ooo.ooo.ooo.ooo.",
        "................",
        "ooo.ooo.ooo.ooo.",
        "ooo.ooo.ooo.ooo.",
        "................",
        "###.###.###.###.",
        "###.###.###.###.",
        "................",
        "ooo.ooo.ooo.ooo.",
        "ooo.ooo.ooo.ooo.",
        "................",
        "ooo.ooo.ooo.ooo.",
        "ooo.ooo.ooo.ooo.",
        "................",
    ],
    # picoloop's own 4x4 step grid, two steps lit.
    "picoloop": [
        "###..ooo.ooo.ooo",
        "###..ooo.ooo.ooo",
        "###..ooo.ooo.ooo",
        "................",
        "ooo.ooo..###.ooo",
        "ooo.ooo..###.ooo",
        "ooo.ooo..###.ooo",
        "................",
        "ooo.ooo.ooo..ooo",
        "ooo.ooo.ooo..ooo",
        "ooo.ooo.ooo..ooo",
        "................",
        "ooo.ooo.ooo..ooo",
        "ooo.ooo.ooo..ooo",
        "ooo.ooo.ooo..ooo",
        "................",
    ],
}

# name, wordmark, subtitle, accent colour
SYSTEMS = [
    ("synth",    "SYNTH",    "FLUIDSYNTH",      (255, 177,  59)),
    ("chiptune", "CHIPTUNE", "GAME MUSIC EMU",  ( 92, 224, 123)),
    ("adlib",    "ADLIB",    "OPL3 FM",         ( 89, 200, 255)),
    ("lgpt",     "LGPT",     "LITTLEGPTRACKER", (255, 107, 214)),
    ("picoloop", "PICOLOOP", "STEP SEQUENCER",  (184, 140, 255)),
]

LIGHT = (242, 242, 242)
SHADOW = (24, 24, 28)

ICON_PX, TITLE_PX, SUB_PX = 7, 6, 3
MARGIN, GAP = 12, 20


def glyph_rects(text, x, y, px, colour):
    """Pixel rectangles for a string in the 5x7 font."""
    out = []
    for ch in text.upper():
        rows = FONT.get(ch, FONT[" "]).split("|")
        for ry, row in enumerate(rows):
            for rx, cell in enumerate(row):
                if cell == "#":
                    out.append((x + rx * px, y + ry * px, px, px, colour))
        x += 6 * px
    return out, x


def text_width(text, px):
    return len(text) * 6 * px - px


def build(name, title, subtitle, accent):
    icon = ICONS[name]
    rects = []
    icon_w = len(icon[0]) * ICON_PX
    icon_h = len(icon) * ICON_PX
    title_h, sub_h = 7 * TITLE_PX, 7 * SUB_PX
    block_h = title_h + 8 + sub_h
    height = MARGIN * 2 + max(icon_h, block_h)
    text_x = MARGIN + icon_w + GAP
    width = text_x + max(text_width(title, TITLE_PX), text_width(subtitle, SUB_PX)) + MARGIN

    iy = (height - icon_h) // 2
    for ry, row in enumerate(icon):
        for rx, cell in enumerate(row):
            if cell in "#o":
                colour = accent if cell == "#" else LIGHT
                rects.append((MARGIN + rx * ICON_PX, iy + ry * ICON_PX, ICON_PX, ICON_PX, colour))

    ty = (height - block_h) // 2
    rects += glyph_rects(title, text_x, ty, TITLE_PX, LIGHT)[0]
    rects += glyph_rects(subtitle, text_x, ty + title_h + 8, SUB_PX, accent)[0]

    # A hard pixel shadow under everything: the logo has to stay readable on a
    # light theme background as well, and nanosvg has no filters.
    shadows = [(x + max(2, w // 3), y + max(2, h // 3), w, h, SHADOW)
               for x, y, w, h, _ in rects]
    return width, height, shadows + rects


def write_svg(path, width, height, rects):
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d">'
             % (width, height, width, height)]
    for x, y, w, h, (r, g, b) in rects:
        parts.append('<rect x="%d" y="%d" width="%d" height="%d" fill="#%02x%02x%02x"/>'
                     % (x, y, w, h, r, g, b))
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n")


def write_png(path, width, height, rects):
    """RGBA, transparent background - the same rectangles, rasterised."""
    buf = bytearray(width * height * 4)
    for x, y, w, h, (r, g, b) in rects:
        for yy in range(y, min(y + h, height)):
            row = yy * width * 4
            for xx in range(x, min(x + w, width)):
                i = row + xx * 4
                buf[i:i + 4] = bytes((r, g, b, 255))
    raw = b"".join(b"\x00" + bytes(buf[y * width * 4:(y + 1) * width * 4]) for y in range(height))

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, title, subtitle, accent in SYSTEMS:
        width, height, rects = build(name, title, subtitle, accent)
        write_svg(OUT / (name + ".svg"), width, height, rects)
        write_png(OUT / (name + ".png"), width, height, rects)
        print("%-9s %dx%d  %d rects" % (name, width, height, len(rects)))


if __name__ == "__main__":
    main()
