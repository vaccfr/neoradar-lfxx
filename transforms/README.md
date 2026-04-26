# Transforms

Pulls files from the private `data-sectorfiles` repo into this package and
applies literal-string replacements on the way through. Run by the release
workflow; can be run locally for testing too.

## Files

- `replacements.json` — declares each `source` (relative to the live-data
  repo root) → `target` (relative to this repo root), with an optional list
  of `{find, replace}` pairs applied in order.
- `apply.py` — reads the config and copies/transforms each file.

## Adding a new sync target

Append an entry to `files[]` in `replacements.json`:

```json
{
  "source": "LFXX/Settings/SomeFile.txt",
  "target": "euroscope_data/SomeFile.txt",
  "replacements": [
    { "find": "UPSTREAM_PLACEHOLDER", "replace": "our_value" }
  ]
}
```

Replacements are plain string substitutions (not regex). Paste the literal
upstream text. The script warns if a `find` produces zero matches, which
usually means upstream changed wording and the rule needs updating.

## Local test run

```bash
python3 transforms/apply.py /path/to/data-sectorfiles
```

Sector files (`.ese` / `.sct`) are handled separately in the workflow
because their filenames rotate per AIRAC.
