#!/usr/bin/env python3
"""
Sync upstream live-data files into the package, applying configured
literal-string replacements on the way through.

Usage: apply.py <live-data-root> [--config transforms/replacements.json]

The config lists files to copy from <live-data-root>/<source> into <target>
(relative to the repo root, i.e. this script's parent's parent), with any
number of literal find/replace pairs applied in order. Replacements are
plain string substitutions, not regex — paste literal upstream text.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def apply_file(live_root: Path, repo_root: Path, entry: dict) -> None:
    src = live_root / entry["source"]
    dst = repo_root / entry["target"]
    replacements = entry.get("replacements", [])

    if not src.is_file():
        raise SystemExit(f"::error::Missing upstream file: {src}")

    data = src.read_bytes()
    for r in replacements:
        find = r["find"].encode("utf-8")
        replace = r["replace"].encode("utf-8")
        before = data.count(find)
        if before == 0:
            print(
                f"::warning::No match for {r['find']!r} in {entry['source']} "
                f"— upstream may have changed wording.",
                file=sys.stderr,
            )
            continue
        data = data.replace(find, replace)
        print(f"  {entry['source']}: replaced {before}× {r['find']!r}")

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    print(f"-> {entry['target']} ({len(data)} bytes)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("live_root", help="Path to checked-out live-data repo")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).with_name("replacements.json")),
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    live_root = Path(args.live_root).resolve()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))

    for entry in config["files"]:
        apply_file(live_root, repo_root, entry)

    return 0


if __name__ == "__main__":
    sys.exit(main())
