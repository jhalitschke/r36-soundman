#!/usr/bin/env python3
"""Cheap checks on the README, for the two ways documentation rots silently.

A mermaid block with an unbalanced `end` renders as an error box on GitHub and
nowhere else, so nobody editing locally would notice. A link to a file that has
been renamed is the same kind of quiet wrong. Neither needs a browser to catch.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
TEXT = README.read_text()

# the ones mermaid actually has; a typo here is an error box on GitHub
KINDS = (
    "flowchart", "graph", "sequenceDiagram", "classDiagram", "stateDiagram",
    "erDiagram", "gantt", "pie", "journey", "gitGraph", "mindmap", "timeline",
)


def blocks():
    return re.findall(r"```mermaid\n(.*?)```", TEXT, re.S)


class Mermaid(unittest.TestCase):
    def test_there_are_diagrams(self):
        self.assertTrue(blocks(), "the README has no mermaid at all")

    def test_each_declares_a_real_diagram_type(self):
        for i, b in enumerate(blocks(), 1):
            with self.subTest(diagram=i):
                first = next(l.strip() for l in b.splitlines() if l.strip())
                self.assertTrue(
                    first.startswith(KINDS),
                    "first line is %r, which mermaid will not recognise" % first,
                )

    def test_subgraphs_are_closed(self):
        """An unbalanced end is the mistake that renders as an error box."""
        for i, b in enumerate(blocks(), 1):
            with self.subTest(diagram=i):
                opens = len(re.findall(r"^\s*subgraph\b", b, re.M))
                closes = len(re.findall(r"^\s*end\s*$", b, re.M))
                self.assertEqual(opens, closes, "%d subgraph, %d end" % (opens, closes))

    def test_labels_with_punctuation_are_quoted(self):
        """Unquoted brackets or slashes in a label break the parse."""
        for i, b in enumerate(blocks(), 1):
            with self.subTest(diagram=i):
                for label in re.findall(r"\[([^\]\n]*)\]", b):
                    if any(c in label for c in "/*()·"):
                        self.assertTrue(
                            label.startswith('"') and label.endswith('"'),
                            "label %r needs quoting" % label,
                        )


class Links(unittest.TestCase):
    def test_links_into_the_repo_resolve(self):
        """[text](scripts/foo.py) after a rename is a quiet lie."""
        missing = []
        for target in re.findall(r"\]\(([^)#\s]+)\)", TEXT):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            if not (ROOT / target).exists():
                missing.append(target)
        self.assertEqual(missing, [], "README links to files that are not there")


if __name__ == "__main__":
    unittest.main(verbosity=2)
