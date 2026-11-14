# neoradar-lfxx

NeoRadar packages for the French vACC, built from the French vACC Controller Pack
([vaccfr/Sector-Files](https://github.com/vaccfr/Sector-Files)) and the GNG AIRAC data.

TO BE USED SOLELY ON THE VATSIM NETWORK - NOT TO BE USED FOR REAL WORLD AVIATION PURPOSES

## Packages

GNG publishes one sector file per FIR group, so there is one NeoRadar package per GNG file:

| Package | FIRs | Namespace | Provider URL |
| --- | --- | --- | --- |
| `LFBB` | Bordeaux | `lfbb` | `https://pkg.neoradar.app/lfbb` |
| `LFXXN` | Paris + Reims (GNG's combined `LFXXN` file) | `lfxxn` | `https://pkg.neoradar.app/lfxxn` |
| `LFMM` | Marseille | `lfmm` | `https://pkg.neoradar.app/lfmm` |
| `LFRR` | Brest | `lfrr` | `https://pkg.neoradar.app/lfrr` |

Each package carries:

- the GNG sector file converted by `neoradar-cli` (maps, NSE, ATC data, `radars.json`);
- the FIR's EuroScope ASRs as NeoRadar profiles. A CoFrance display gets the ATM system of its
  `PLUGIN:CoFrance:TagFormat` and CoFrance's altitude filter; an AVISO (vSMR) display gets the
  `default` ground system and its airport's AVISO / ground layout items;
- one ATM system per CoFrance tag format. IRMA, Paris-CDG and Nice have hand-made ports in
  `shared/package/systems` (`irma`, `cdg`, `nce`), and the rule-less `default` format the FIR/UIR
  displays use is CoFrance's base look, the `default` system; every other format the package's ASRs use is
  generated at build time by `scripts/tag_formats.py` as `cf-<format>`: `irma`'s label rows (all
  formats share one tag layout) with the tag colours, leader lines and track symbols of the format's
  rules, in CoFrance's priority order;
- the **CoFrance maps** of its FIRs (plus the shared `LFXX` coastlines) as NeoRadar map layers,
  `datasets/maps/cofrance-<fir>[-<sector>].geojson`, one toggleable item per CoFrance map. A
  profile converted from a CoFrance ASR turns on exactly the maps its `EnabledMaps` line names;
- the login profiles, aliases, ICAO data (with RECAT-EU) and the shared systems, fonts, images
  and sounds in `shared/package/`.

Packages ship **no plugins**: the C# NeoRadar client only loads C# SDK plugins, and the old C++
ones (NeoCCAMS, NeoVACDM, NeoRPC, NeoRampAgent, the VATCAN lua script) cannot load in it. The
labels and the CDM list still name `plugin:NeoVSID:*` and `plugin:NeoVACDM:*` items; they render
empty until C# ports with the same ids exist.

## What is (and is not) in git

Committed: the build scripts, `packages.json`, `shared/` (systems, fonts, images, sounds, RECAT),
`transforms/`, `diffs/` and the workflows.

**Never committed**: GNG sector files (`.sct`, `.ese`), anything built (`build/`, `dist/`, zips),
`server-dataset.json` and the airways databases. `.gitignore` covers them and the Validate
workflow fails if one is tracked.

## Building locally

Needs Python 3.10+, Node 24 and [neoradar-cli](https://github.com/neoradar-project/cli) from its
`develop` branch: current clients refuse layer files without an item table, which `main` does not
write yet. The release workflow pins `NEORADAR_CLI_REF`/`NEORADAR_SCHEMAS_REF` to `develop` for that reason.
The source tree is a French vACC Controller Pack folder as the installer leaves it (Sector-Files,
the CoFrance maps the loader downloaded, and the GNG `LFXX/Sectors/*.sct|.ese`, `<FIR>/ICAO`,
`<FIR>/NavData`):

```bash
# all packages; NEORADAR_CLI defaults to `neoradar-cli`
NEORADAR_CLI="node ../neoradar-cli/dist/index.js" scripts/build-all.sh ~/Documents/FrenchVACC
# or a subset
scripts/build-all.sh ~/Documents/FrenchVACC LFRR,LFBB

# schema check (ajv + js-yaml: npm install --no-save --prefix scripts ajv@8 js-yaml@4)
node scripts/validate.js ../schemas build/*/package

# zip one package for a local test, drop the folder in Documents/NeoRadar/packages
cd build && neoradar-cli distribute LFRR --new-version 2611_local
```

`scripts/build-all.sh` runs three steps per package:

1. `scripts/build.py assemble` writes `build/<ID>/`, a fresh neoradar-cli environment: sector
   files renamed `<ID>.sct/.ese`, ASRs (re-encoded UTF-8), concatenated login profiles with the
   `transforms/` replacements, ICAO data, NavData, `shared/package`, the manifest and the
   converted CoFrance maps; then applies `diffs/common/*.patch` and `diffs/<ID>/*.patch`.
2. `neoradar-cli convert build/<ID>`.
3. `scripts/build.py finalize` sets each profile's ATM system, transition altitude, altitude
   filter and CoFrance map items, and drops manifest layers with no dataset.

## Releasing

Run **Publish Release** (`workflow_dispatch`). It checks out `vaccfr/Sector-Files`, puts
[alexisBalzano/CoFrance-config-files](https://github.com/alexisBalzano/CoFrance-config-files) in
`LFXX/Plugins/CoFrance` (Sector-Files ships only the CoFrance loader, which downloads the maps from
there at runtime), lays the private `data-sectorfiles` repo over both, builds and validates every package, builds the
server-only airways databases, then runs `neoradar-cli distribute --publish` per package with
version `<AIRAC>_<sha7>`. Zips and server artifacts are uploaded as workflow artifacts.

`data-sectorfiles` holds exactly the files the Controller Pack Installer treats as GNG-owned
(`installer/core/src/pack_sync/ownership.rs` in Sector-Files), at their install paths:

```text
LFXX/Sectors/current_airac.txt        e.g. 2611
LFXX/Sectors/LFBB.sct, LFBB.ese       one pair per FIR (LFFF and LFEE are the same LFXXN file)
LFXX/Sectors/LFFF.sct, LFFF.ese
LFXX/Sectors/LFMM.sct, LFMM.ese
LFXX/Sectors/LFRR.sct, LFRR.ese
<FIR>/ICAO/ICAO_Aircraft.txt, ICAO_Airlines.txt, ICAO_Airports.txt
<FIR>/NavData/airway.txt, isec.txt, icao.txt
<FIR>/Settings/VoiceChannels.txt
LFXX/ICAO/, LFXX/NavData/
```

Nothing else: anything else in it would overwrite the fresher public copy.

Each AIRAC: copy those files from an up-to-date Controller Pack install into `data-sectorfiles`,
push, run the workflow.

## Adding or changing a package

Edit `packages.json`: `sectorFile` is the basename in `LFXX/Sectors/`, `firs` the source folders
for ASRs, settings, ICAO, NavData and CoFrance maps. The publish path and provider URL come from
the namespace.
