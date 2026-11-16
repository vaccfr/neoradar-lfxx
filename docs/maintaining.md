# Maintaining the French NeoRadar packages

This repo turns the French vACC's EuroScope Controller Pack into one NeoRadar package, `LFXX`. It holds
only scripts and settings: every build starts from the upstream sources, so most changes belong
upstream, and a release is mostly "update the data, run the workflow".

## How it fits together

```text
vaccfr/Sector-Files (public)              ASRs, login profiles, aliases
alexisBalzano/CoFrance-config-files       CoFrance maps and tag formats
vaccfr/data-sectorfiles (PRIVATE)         GNG sector files, ICAO, NavData
                │
                ▼  laid over each other into one "source tree"
   scripts/build.py assemble   → build/<ID>/        one neoradar-cli environment per package
   neoradar-cli convert        → build/<ID>/package the converted package
   scripts/build.py finalize   → profiles finished, manifest cleaned
   scripts/validate.js         → checked against the NeoRadar schemas
   neoradar-cli distribute     → zip + publish to pkg.neoradar.app
```

`scripts/build-all.sh` runs the first three steps; the **Publish Release** workflow runs them all.

| Package | Built from | FIR folders |
| --- | --- | --- |
| `LFXX` | `LFXX/Sectors/LFFM.sct/.ese` (the military GNG file, all French FIRs) | LFFF, LFEE, LFRR, LFBB, LFMM, LFFM |

It is defined in `packages.json`. ASRs, login profiles and CoFrance maps come from every FIR folder
listed (the first FIR wins a duplicated callsign); ICAO and NavData come from `LFFM` (`dataFolder`).
The per-FIR GNG files (`LFBB`, `LFFF`, `LFEE`, `LFMM`, `LFRR`) are no longer used.

## Each AIRAC

1. Update your Controller Pack with the French vACC installer so it has the new GNG files.
2. Copy the GNG files into your clone of `vaccfr/data-sectorfiles`, at the same paths:
   - `LFXX/Sectors/`: the military file renamed `LFFM.sct` / `LFFM.ese`, and `current_airac.txt`
   - `LFXX/ICAO/`, `LFXX/NavData/`
   - `LFFM/ICAO/`, `LFFM/NavData/` (from the military download)
   - for each of LFBB, LFEE, LFFF, LFMM, LFRR: `Settings/VoiceChannels.txt`

   Copy nothing else: anything else in that repo overrides the public Sector-Files copy.
3. Commit as the AIRAC (e.g. `2612`) and push.
4. Run **Publish Release** (below).
5. Upload the server datasets (below).

## Releasing

GitHub → Actions → **Publish Release** → Run workflow.

- **packages**: leave empty (there is only `LFXX`).
- **publish**: untick to only build. The zips are then in the run's artifacts, to try first.

The run fails on a missing input, a convert error or a schema error, before anything is
published. Read its warnings either way (see [Build warnings](#build-warnings)).

Versions are `<AIRAC>_<commit>`, e.g. `2611_b7bea4a`.

### Server datasets

Each build also writes `build/<ID>/server-dataset.json` (procedures, positions, sectors,
navaids). The NeoRadar server needs it for routes, procedures and runway suggestions. It is in the
run's `server-artifacts-<sha>` artifact. Upload each one with a staff token:

```bash
NEORADAR_STAFF_TOKEN=... neoradar-cli push-dataset build/LFXX
```

It shows what changes on the server and publishes only after you type the vAcc id.

## Building locally

You need Python 3.10+, Node 24, pnpm 10, and neoradar-cli from its `develop` branch:

```bash
pnpm add -g "github:neoradar-project/cli#develop"
```

Build from your Controller Pack folder (it already has everything laid out):

```bash
scripts/build-all.sh ~/Documents/FrenchVACC
```

To try a package in NeoRadar, link it into the packages folder (Windows, PowerShell):

```powershell
New-Item -ItemType Junction -Path "$env:USERPROFILE\Documents\NeoRadar\packages\LFXX" `
  -Target "$PWD\build\LFXX\package"
```

Close NeoRadar before rebuilding: the build deletes and recreates `build/<ID>`.

To check against the schemas:

```bash
npm install --no-save --prefix scripts ajv@8 js-yaml@4
git clone -b develop https://github.com/neoradar-project/schemas ../schemas
node scripts/validate.js ../schemas build/*/package
```

## Making changes

**Fix it upstream when you can.** A wrong ASR, map or position is wrong in EuroScope too. Fix it
in Sector-Files or CoFrance-config-files and it reaches the next build. Use the options below
only for what is NeoRadar-specific or cannot wait.

### Tag colours, labels, symbols (radar systems)

Each profile gets the system matching its ASR's `PLUGIN:CoFrance:TagFormat`:

| Tag format | System | Where it comes from |
| --- | --- | --- |
| IRMA | `irma` | hand-made, `shared/package/systems/irma` |
| Paris-CDG | `cdg` | hand-made |
| Nice | `nce` | hand-made |
| `default` (FIR / UIR displays) and AVISO displays | `default` | hand-made, CoFrance's base look |
| every other format (Seine, Lyon, Paris-Orly…) | `cf-<format>` | generated at build time |

- **Hand-made systems**: edit the files in `shared/package/systems/<name>/`.
- **Generated systems**: colours, symbols and which flights get them come from CoFrance's
  `tag_formats.json`, so change them there. The tag *content* (rows and items) is copied from
  `irma`: change `irma`'s labels and every generated system follows.
- Rules shared by all systems live in `shared/package/systems/expressions.json`.

The schemas describe every field: <https://github.com/neoradar-project/schemas> (`systems/`).

### Maps

- **CoFrance maps** are converted from the CoFrance config repo on every build
  (`scripts/cofrance.py`). Each CoFrance folder becomes one layer named "CoFrance …" and each map
  file one toggle. A CoFrance ASR's `EnabledMaps` line decides which ones its profile shows.
- **Sector-file maps** come from the GNG `.sct` via neoradar-cli.

### Profiles

Profiles are converted from the ASRs on every build, then `finalize` adds:

- CoFrance displays: the system, transition altitude 5000, CoFrance's altitude filter and maps.
- AVISO displays: the `default` system and the airport's `<ICAO> AVISO` region and
  `<ICAO> Groundlayout AVISO` geo. Airports without those get their ground layout and runways.

To change a profile, change its ASR upstream.

### Patching upstream files

To change a source file before conversion without waiting for upstream, add a patch under
`diffs/<ID>/` (or `diffs/common/` for every package). See [diffs/README.md](../diffs/README.md).
For a simple text swap, use `transforms/replacements.json` (see
[transforms/README.md](../transforms/README.md)).

### Adding a package

Add an entry to `packages.json`: `id`, `name`, `namespace` (stable forever, it is the provider URL
and the server's vAcc id), `sectorFile` (basename in `LFXX/Sectors/`) and `firs` (source folders).

## Build warnings

The build prints warnings instead of failing for problems in the upstream data. Most need a fix
upstream.

| Warning | Meaning | What to do |
| --- | --- | --- |
| `ESE positions with no identifier, dropped` | GNG listed a position without its id; it would break the client | Report to the GNG/sector file maintainers |
| `… names N object(s) the sector file does not have, dropped` | An ASR names a runway, navaid or map that is gone (renumbered, withdrawn) | Fix the ASR in Sector-Files |
| `CoFrance maps named by ASRs but absent` | An ASR enables a CoFrance map that does not exist | Fix the ASR or add the map in CoFrance-config-files |
| `sets vSMR:Airport:X; using Y from its name` | An AVISO ASR points at the wrong airport | Fix the ASR in Sector-Files |
| `AVISO displays drawing runways only` | The sector file has no ground layout for that airport | Nothing, or ask for a ground layout in GNG |
| `tag format …: rule … skipped, unsupported condition` | CoFrance added a condition the generator does not know | Extend `scripts/tag_formats.py` |
| `replacement … matched nothing` | Upstream changed text a transform expects | Update `transforms/replacements.json` |
| `ESE Parsing error` (neoradar-cli) | A malformed line in the GNG file, e.g. a SID with no route | Usually harmless; report to GNG if it matters |

## Known limits

- **No plugins.** The C# NeoRadar client only loads C# plugins; the old C++ ones (vACDM, CCAMS,
  RPC, RampAgent, VATCAN) do not load. Labels still name `plugin:NeoVSID:*` and
  `plugin:NeoVACDM:*` items, which stay empty until C# ports exist.
- **Server-dependent tags.** Arrival runway colours (CDG), SID/runway suggestions and route-based
  rules need the server link and the uploaded server dataset.
- **Not converted yet:** vSID procedure priorities and runway preferences.
- **CLI pinned to `develop`.** Current clients need files only neoradar-cli `develop` writes. When
  `develop` is merged, set `NEORADAR_CLI_REF` and `NEORADAR_SCHEMAS_REF` back to `main` in
  `.github/workflows/release.yml` and `ref:` in `validate.yml`.

## Secrets used by the workflows

| Name | For |
| --- | --- |
| `LIVE_DATA_APP_ID` (variable), `LIVE_DATA_APP_PRIVATE_KEY` (secret) | Reading the private `data-sectorfiles` repo |
| `AWS_PUBLISH_CREDENTIALS` | Uploading packages to the package bucket |
