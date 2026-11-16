# Diffs

Patches applied to a package environment by `scripts/build.py assemble`, after the source
files are copied in and **before** `neoradar-cli convert` runs.

| Folder | Applied to |
| --- | --- |
| `diffs/common/*.patch` | every package |
| `diffs/<ID>/*.patch` | `build/<ID>/` only (`LFXX`) |

Patches apply in filename order with `git apply --whitespace=fix --directory=build/<ID>`, so
paths inside a patch are relative to the environment root:

| Path in the patch | File |
| --- | --- |
| `sector_files/<ID>.ese`, `sector_files/<ID>.sct` | the GNG sector file, renamed to the package id |
| `ASRs/...` | the FIR's ASRs (`ASRs/LFFF/...`, `ASRs/LFEE/...`, one folder per FIR) |
| `euroscope_data/Alias.txt`, `euroscope_data/LoginProfiles.txt` | aliases, login profiles |
| `icao_data/ICAO_*.txt` | ICAO data |
| `package/...` | the package itself, e.g. a generated CoFrance map layer |

A patch that no longer applies fails the build: upstream changed under it.

## Authoring a patch

```bash
python scripts/build.py assemble --source ~/Documents/FrenchVACC --only LFXX
cp build/LFXX/sector_files/LFXX.ese /tmp/LFXX.ese.orig
# edit build/LFXX/sector_files/LFXX.ese
git diff --no-index /tmp/LFXX.ese.orig build/LFXX/sector_files/LFXX.ese \
  | sed -e 's#a/tmp/LFXX.ese.orig#a/sector_files/LFXX.ese#' -e 's#b/build/LFXX/#b/#' \
  > diffs/LFXX/fix-something.patch
```

The headers must read `a/sector_files/LFXX.ese` / `b/sector_files/LFXX.ese`. Keep one logical
change per patch.

**A patch against a `.sct` or `.ese` quotes the restricted sector file it changes.** Keep those
patches to the lines you change (default 3 lines of context) and never commit a whole-file diff.
