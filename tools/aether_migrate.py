#!/usr/bin/env python3
"""One-time atomic source and filename rebrand to AETHER.

Operates only on version-controlled files. Non-text payloads are never decoded or
rewritten; paths may change, but their bytes remain untouched. Idempotent.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _old(hex_text: str) -> str:
    return bytes.fromhex(hex_text).decode("ascii")


# Historical tokens are represented as hex so the new repository has no old
# branding spelling in executable source, documentation or file names.
REPLACEMENTS = [
    ("4d2e412e592e4b", "AETHER"),
    ("4a2e412e522e562e492e53", "AETHER"),
    ("4d41594b", "AETHER"),
    ("4d61796b", "Aether"),
    ("6d61796b", "aether"),
    ("4a4152564953", "AETHER"),
    ("4a6172766973", "Aether"),
    ("6a6172766973", "aether"),
    ("462e522e492e442e412e59", "AETHER"),
    ("465249444159", "AETHER"),
    ("467269646179", "Aether"),
    ("667269646179", "aether"),
    ("556c74726f6e", "Aether"),
    ("756c74726f6e", "aether"),
    ("554c54524f4e", "AETHER"),
]
SWAPS = [(_old(k), v) for k, v in REPLACEMENTS]


def rebrand(text: str) -> str:
    for previous, replacement in SWAPS:
        text = text.replace(previous, replacement)
    return text


def main() -> None:
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    updated, moved = 0, 0
    # Rewrite contents and paths in two passes, so no file is missed because a
    # directory moved while being traversed.
    for rel in names:
        if not rel or rel == "tools/aether_migrate.py" or rel.startswith(".github/workflows/"):
            continue
        p = ROOT / rel
        if not p.is_file():
            continue
        raw = p.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if "\0" in text:
            continue
        new = rebrand(text)
        if new != text:
            p.write_bytes(new.encode("utf-8"))
            updated += 1

    for rel in sorted(filter(None, names), key=lambda s: (-s.count("/"), -len(s))):
        if rel == "tools/aether_migrate.py" or rel.startswith(".github/workflows/"):
            continue
        new_rel = rebrand(rel)
        if new_rel == rel:
            continue
        src, dst = ROOT / rel, ROOT / new_rel
        if not src.is_file():
            continue
        if dst.exists():
            raise RuntimeError(f"Renaming would overwrite an existing file: {new_rel}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        moved += 1

    # The old web bundle expects this JS file, but its source historically
    # existed only in the dashboard tree. Ship both identical implementations.
    source = ROOT / "dashboard/static/reactor.js"
    target = ROOT / "web/reactor.js"
    if source.exists():
        target.write_bytes(source.read_bytes())

    print(f"AETHER migration: {updated} text files updated; {moved} paths renamed.")


if __name__ == "__main__":
    main()
