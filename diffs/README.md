# Diffs

Patches in this folder are applied on top of the live data pulled from the
private `data-sectorfiles` repo, **before** the `neoradar-cli` conversion runs.

Anything under `diffs/**/*.patch` is applied, sorted by path.

## Layout

| Folder | Targets |
| --- | --- |
| `diffs/sector_files/` | `LFXX.ese`, `LFXX.sct`, `LFXX.sct2` |
| `diffs/icao_data/` | `ICAO_Aircraft.txt`, `ICAO_Airlines.txt`, `ICAO_Airports.txt` |
| `diffs/euroscope_data/` | `Alias.txt`, `LoginProfiles.txt` |

## Stable filenames

The release workflow renames the AIRAC-rotating sector files to stable
paths **before** patching, so your patches don't break every month:

| Upstream (`data-sectorfiles`) | Patched as |
| --- | --- |
| `LFXX-LFXX_<airac-stamp>.ese` | `sector_files/LFXX.ese` |
| `LFXX-LFXX_<airac-stamp>.sct` | `sector_files/LFXX.sct` |
| `LFXX-LFXX_<airac-stamp>.sct2` | `sector_files/LFXX.sct2` *(if present)* |

> Always author patches against `sector_files/LFXX.ese` / `LFXX.sct` etc. —
> **never** against the dated upstream filename.

Other targets keep their upstream names: `ICAO_*.txt`, `Alias.txt`,
`LoginProfiles.txt`.

## Authoring a patch

1. **Reproduce the post-sync state locally.** Either run the workflow's
   sync logic against a checkout of `data-sectorfiles`, or just copy the
   relevant file into place under its stable name:

   ```bash
   cp /path/to/data-sectorfiles/LFXX-LFXX_*.sct sector_files/LFXX.sct
   ```

   These targets are `.gitignore`d so git won't pick them up directly.

2. **Edit the file in place.**

3. **Generate a patch** with paths relative to the repo root:

   ```bash
   git diff --no-index --relative \
     sector_files/LFXX.sct sector_files/LFXX.sct \
     > diffs/sector_files/fix-something.patch
   ```

   Or, if the file is temporarily un-ignored:

   ```bash
   git diff sector_files/LFXX.sct > diffs/sector_files/fix-something.patch
   ```

4. **Commit the `.patch` file.** CI applies it with:

   ```bash
   git apply --whitespace=fix <patch>
   ```

Keep one logical change per patch so PRs stay reviewable.
