# Maintaining the French NeoRadar packages

This repo turns the French vACC's EuroScope Controller Pack into one NeoRadar package, `LFXX`. It holds
only scripts and settings: every build starts from the upstream sources, so most changes belong
upstream, and a release is mostly "update the data, run the workflow".

## How it fits together

```text
vaccfr/Sector-Files (public)              ASRs, login profiles, aliases
alexisBalzano/CoFrance-config-files       CoFrance maps
vaccfr/data-sectorfiles (PRIVATE)         GNG sector files, ICAO, NavData
                │
                ▼  laid over each other into one "source tree"
   scripts/build.py assemble   → build/<ID>/        one neoradar-cli environment per package
   neoradar-cli convert        → build/<ID>/package the converted package
   scripts/build.py finalize   → profiles finished, manifest cleaned
   scripts/validate.js         → checked against the NeoRadar schemas
   neoradar-cli distribute     → zip + publish to the R2 bucket, served at pkg.neoradar.app
```

`scripts/build-all.sh` runs the first three steps; the **Publish Release** workflow runs them all.

| Package | Built from | FIR folders |
| --- | --- | --- |
| `LFXX` | `LFXX/Sectors/LFFM.sct/.ese` (the military GNG file, all French FIRs) | LFFF, LFEE, LFRR, LFBB, LFMM, LFFM |

It is defined in `packages.json`. ASRs, login profiles and CoFrance maps come from every FIR folder
listed (the first FIR wins a duplicated callsign); ICAO and NavData come from `LFFM` (`dataFolder`).
The per-FIR GNG files (`LFBB`, `LFFF`, `LFEE`, `LFMM`, `LFRR`) are no longer used.

NeoRadar is used for approach and below for now, so the centre displays are left out:
`excludeAsrs` in `packages.json` lists them as globs (`* FIR.asr`, `* UIR.asr`, `* CTR.asr`; and
`* Legacy APP.asr`, the old approach displays the CoFrance ones replace), and
the build log names every ASR it skipped. The centre login profiles go too: `excludeLoginFacilities`
lists EuroScope facility numbers (`6` is centre). Remove a pattern to ship those displays again (they
would then need a system: see below).

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
- **revision**: 1 for the first release of an AIRAC, then 2, 3… (the version is `<AIRAC>.<revision>`).
- **publish**: untick to only build. The zips are then in the run's artifacts, to try first.

The package goes to the Cloudflare R2 bucket `neoradar-packages` under `lfxx/`, which
`https://pkg.neoradar.app/lfxx` serves (the provider URL controllers add). `publish` in
`packages.json` holds the bucket, endpoint and the names of the two key variables; the keys
themselves are repository secrets (below).

The run fails on a missing input, a convert error or a schema error, before anything is
published. It also fails if publishing was asked for and the R2 secrets are missing, or if
`neoradar-cli distribute` does not report the package published. Read its warnings either way (see [Build warnings](#build-warnings)).

Record what each release changes in `changelog/<AIRAC>.txt` (one file per AIRAC, a line per
revision), and batch changes into a release rather than publishing each one.

Versions are `<AIRAC>.<revision>`, e.g. `2611.1`: **revision** is a workflow input, 1 for the first
release of a cycle. To republish within the same AIRAC, run it again with the next revision
(`2611.2`). The client offers an update whenever the published version differs from the
installed one, so never reuse a version for different content.

### Server datasets

Each build also writes `build/<ID>/server-dataset.json` (procedures, positions, sectors,
navaids). The NeoRadar server needs it for routes, procedures and runway suggestions. It is in the
run's `server-artifacts-<sha>` artifact. Upload each one with a staff token:

```bash
NEORADAR_STAFF_TOKEN=... neoradar-cli push-dataset build/LFXX
```

It shows what changes on the server and publishes only after you type the vAcc id.

## Building locally

You need Python 3.10+, Node 24, pnpm 10, and neoradar-cli from its `main` branch:

```bash
pnpm add -g "github:neoradar-project/cli#main"
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
git clone https://github.com/neoradar-project/schemas ../schemas
node scripts/validate.js ../schemas build/*/package
```

## Making changes

**Fix it upstream when you can.** A wrong ASR, map or position is wrong in EuroScope too. Fix it
in Sector-Files or CoFrance-config-files and it reaches the next build. Use the options below
only for what is NeoRadar-specific or cannot wait.

### Tag colours, labels, symbols (radar systems)

There are two systems, both static files in `shared/package/systems/`, edited by hand. The build
no longer reads CoFrance's `tag_formats.json`: when CoFrance changes a colour or rule, port it here.

| System | Used by | Track logic from |
| --- | --- | --- |
| `neoirma` | every CoFrance approach display except Paris-CDG, and every AVISO (ground) display | CoFrance tag format `IRMA` |
| `cdg` | the Paris-CDG approach (`PLUGIN:CoFrance:TagFormat:Paris-CDG`), and the LFPG and LFPB AVISOs (`SYSTEM_FOR_AVISO`) | CoFrance tag format `Paris-CDG` |

`SYSTEM_FOR_TAG_FORMAT` in `scripts/build.py` maps tag formats to systems; anything else gets
`neoirma`. neoIRMA is a stripless IRMA, not the real-world one. Its `ground` section (labels and
targets) is the package's only ground look: the AVISO look, raw video with a small ring. `cdg`'s
`ground` and `groundSymbology` are `"#neoirma"`, a reference to it.

**Track colours** follow the CoFrance rules in their priority order (the first matching variant
wins, as CoFrance's lowest priority number does):

- `neoirma`: departures pink `#D597A3`, arrivals blue `#63BBD9`, everything else a quiet grey
  `#8E8E8E`. Departure and arrival are NeoRadar's `isDeparture` / `isArrival`: the plan leaves
  from or lands at an airport the controller has active (with runways set), not CoFrance's
  "any `LF*` airport".
- `cdg`: CoFrance's Paris-CDG letters and colours: `S`/`N` CDG arrivals by runway pair (the
  assigned arrival runway, or the server's suggestion while none is assigned), `B` Le Bourget,
  `O` Orly, `A` Pontoise/Beauvais, `V` Toussus/Villacoublay, `R` CDG with no runway yet, `G`/`P`
  local flights, two-letter departure codes by route point (`NN` NURMO, `EL` LANVI…), `T` other
  Paris departures, black `Z` (VFR) and `X` (the rest).

**Altitude filter.** CoFrance shows flights from a rule with `filtered: false`, and any flight
assumed by you, in transfer to or from you, through the altitude filter. Each variant that does
this lists every `applyToFilterStates`; the tag layouts have a twin keyed on
`$neoirmaThroughFilter` / `$cdgThroughFilter` for the same flights.

**Flight state** is on the callsign. CoFrance's IRMA and Paris-CDG formats colour by flow, not
by state, so the state is shown in reverse video, the same in both systems whatever the flow
(the `assumed…`, `incomingTransfer…` and `handoffText` rules in `expressions.json`):

| State | Callsign |
| --- | --- |
| Assumed | white `242,244,247` on a dark slate plate `30,38,46` |
| Transfer to you | CoFrance's hand-off green `160,216,180` on the same plate |
| Transferred out | hand-off green text, no box |
| Other | the track colour, no box |

The callsign item has `padding: [1, 3]` so the plate does not sit hard against the glyphs.
Boxes in the track colour were hard to tell apart from the map and from each other; one plate
per state, darker than the map, reads at a glance.

Track symbols are vector shapes (`shapes.json`), coloured by each variant's `plotColor`, not
sprites. CDG's letters are 1 px stroke glyphs (`font/A`…`font/Z`, 4 x 6), composed above or below
the disc at a HALF-pixel x (-1.5 for one letter, -4.5 and 1.5 for two). A pixel-bold version (each
glyph drawn twice, one pixel apart) was tried and read too heavy. The client snaps vertical 1 px strokes to pixel
centres but not diagonals, so a glyph at a whole-pixel x gets one straight side and one round one
(O read as D). The CDG disc is three filled rectangles kept inside a 4.5 px radius (every client
fills rectangles) under a 1 px ring at 4.5 px, whose anti-aliased edge makes the disc round: the
client fills a circle (0.4.4) with hard pixel rows, no smoother than the rectangles, and an older
client would draw it hollow. Other polygons fill only when they are axis-aligned rectangles.

Both mapstyles carry the CoFrance route draw (thin `route_line` green, small crosses, fix labels
on a dark plate) and the RDF circle (0.5 NM: the radius is in NM and never clamped, so 10 NM
filled an approach display; `circleThreshold` only hides one smaller than that many pixels).
Trails are vector shapes in the track colour, sized per mark by `historyTrailShape.scaleRamp`
(client 0.4.4): CDG's ring (`cdg/trail`, radius 4.5, stroke 1.3) at 3.5, 3.5, 2.5, 2.5, 1.5,
1.5 px radius, every mark inside the disc's size and on whole pixels (a ring of radius n + 0.5 on
the pixel grid is the crispest a small circle gets); IRMA's 4 px ring (`neoirma/trail`), three
then three at 3 px.
Profiles refresh like a radar (`map.sweepIntervalSeconds`, from `build.py`): approach every
`APPROACH_SWEEP_SECONDS` (2 s), AVISOs every `GROUND_SWEEP_SECONDS` (1 s). Aircraft and trails
move together once per sweep, one trail mark per previous sweep, never one on the aircraft.
Without a sweep the client pins the marks to every `historyTrailsSkipSteps`-th update while the
aircraft moves on every one, so the trail stalls and then jumps. The tag trend arrows are Lucide
icons (`:imove-up-right`…).

**Tags.** The airborne rows are the same in both systems. The detailed tag (hover) shows
everything the compact one does, and more: never let a hover lose an item. While you hand a
flight to another controller (attention state 4), both show that controller's frequency after
the SID, in hand-off green (`nextControllerFrequency`), so you know what to tell the pilot. No runway item: at CDG
the runway is in the track colour and letter, and no other French airport lands on two runways
at once.

**Safety nets** (`policy.json`, the same in both systems): STCA on the client's defaults (TopSky's
thresholds, 2.75 NM / 750 ft below 9500 ft, shown when one of the pair is yours), with the
final-approach corridor (2.5 NM in trail on final) and CDG's simultaneous runway pairs
(`stca.parallel`: arrivals 26L/27R and 08R/09L, departures 26R/27L and 08L/09R); the emergency
squawk (7500 HIJACK, 7600 RADIO FAILURE, 7700 EMERGENCY); RIMCAS on every runway, strips from the
navdata (`runwayMonitoring: {}`). The client draws an alert only where a tag, list or target asks
for it, so:

- every tag has an alert line on top (it collapses when empty): the alert's own words, white on
  red (CoFrance `alert_critical`) blinking until clicked (acknowledge) for an alert, dark on
  orange (CoFrance `alert`) for a warning (RIMCAS stage one); airborne tags add the manual alert
  (MISAP, INBEST, IRREG, WX) in CoFrance's warning yellow;
- the track symbol, and the forced one-minute alert vector, turn red / orange (`=alertTrack`,
  `=warningTrack` first in every `plotColor` and `speedVectorColor`).

No sounds are authored, so the nets are silent. Other nets (CLAM, BUST, MSAW, APW, TCT…) stay
off; MSAW and APW would need `msaw.geojson` / `areas.geojson` datasets.

The lists (`lists.yaml`) draw on CoFrance's list colours, nearly opaque, at 11 px: transparent,
their text could not be read over the map.

Rules and expressions shared by both live in `expressions.json`; `lists.yaml` is shared too.

Both systems draw tags and route-draw labels in B612 Mono LFXX Bold (`fonts/B612MonoLFXX-Bold.ttf`): Airbus/ENAC's
cockpit-display font B612 Mono Bold, with a bar added in the zero so 0 and O differ (B612 draws
them alike). `scripts/font_zero.py` makes it from upstream's `B612Mono-Bold.ttf`. SIL OFL, no
reserved name: keep `B612-OFL.txt` beside it. 12 px takes the width and line height of 13 px
EuroScope, with taller capitals.

**Squawks** come from CCAMS: `squawk.http` in `packages.json` is written to the package manifest
as is (`package/manifest.schema.json` in the schemas describes it). Each system's policy can still
rank or disable it by its name, `CCAMS`. The
schemas describe every field: <https://github.com/neoradar-project/schemas> (`systems/`).
`scripts/validate.js` also checks that every `=rule`, `$expression`, shape and `#system` named in
the systems exists, since the client silently ignores a broken one.

### Maps

- **CoFrance maps** are converted from the CoFrance config repo on every build
  (`scripts/cofrance.py`). Each CoFrance folder becomes one layer named "CoFrance …" and each map
  file one toggle. A CoFrance ASR's `EnabledMaps` line decides which ones its profile shows.
- **AVISO maps** are converted from the vSMR fork's AVISO files
  (`LFXX/Plugins/vSMR/vSMR_Data/AVISO/<ICAO>.geojson` in Sector-Files) on every build
  (`scripts/aviso.py`): one layer "AVISO <ICAO>" per airport, with items for the background, the
  ground layout (surfaces and guidance lines, in vSMR's paint order), each label kind (gates,
  taxiways, TORA…) and each vSMR group. A group named for a direction (LFPG's East / West Arrows)
  draws only while a runway end facing that way is active, for arrivals or departures. Colours
  are the palette the airport's ASR picks (`PLUGIN:vSMR:AvisoColorPalette`), else the file's
  default. Label zoom levels (and CoFrance maps' `zoomin` / `zoomout`) are on CoFrance's 0-10
  zoom scale, each level doubling the scale, 10 about an AVISO's opening view; they become
  `minPixelsPerNm` / `maxPixelsPerNm` through `zoom_px_per_nm` in `scripts/cofrance.py`
  (`ZOOM_10_PX_PER_NM` = 320: level 9 is 160 px/nm, 8 is 80). Gate labels (level 9) therefore show
  when an AVISO opens and hide only once it is zoomed well out. Raise or lower that one constant
  to move every threshold.
  Fix the content itself in Sector-Files: these files are what vSMR draws in EuroScope too.
- **Sector-file maps** come from the GNG `.sct` via neoradar-cli.

### Profiles

Profiles are converted from the ASRs on every build, then `finalize` adds:

- CoFrance displays: the system (`cdg` or `neoirma`), transition altitude 5000, CoFrance's
  altitude filter and maps.
- AVISO displays: the `neoirma` system and exactly their airport's AVISO layer, nothing else.
  An airport with no vSMR AVISO file falls back to the sector file's `<ICAO> AVISO` region and
  `<ICAO> Groundlayout AVISO` geo, or its ground layout and runways.

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
| `AVISO files not named by an ICAO code, not converted` | A variant such as `LFPO_Work.geojson`: vSMR loads `<ICAO>.geojson`, so no ASR selects it | Nothing; it would have overwritten the airport's own AVISO |
| `AVISO displays with no vSMR AVISO file` | No `vSMR_Data/AVISO/<ICAO>.geojson` for that airport; its AVISO comes from the sector file | Ask for the AVISO file in Sector-Files |
| `AVISO ASRs listing map items of their own` | An AVISO ASR names map content; the build replaces it with the airport's AVISO | Fix the ASR in Sector-Files |
| `AVISO … faces <direction> but no runway end does` | A vSMR group named for a direction matches no runway; it then draws whenever listed | Fix the group or the runways in the AVISO file |
| `AVISO displays drawing runways only` | The sector file has no ground layout for that airport | Nothing, or ask for a ground layout in GNG |
| `profiles use systems that shared/package/systems does not have` (fails the build) | `SYSTEM_FOR_TAG_FORMAT` names a system with no folder | Add the system or fix the mapping in `scripts/build.py` |
| `replacement … matched nothing` | Upstream changed text a transform expects | Update `transforms/replacements.json` |
| `ESE Parsing error` (neoradar-cli) | A malformed line in the GNG file, e.g. a SID with no route | Usually harmless; report to GNG if it matters |

## Known limits

- **One plugin.** The package ships `shared/package/plugins/vIFF-CDM-alpha.nrplugin`, the NeoRadar
  port of the CDM plugin ([vaccfr/vIFF-neoradar](https://github.com/vaccfr/vIFF-neoradar)); the
  build lists every `.nrplugin` there in the manifest, and the controller approves it in Plugin
  Settings. To update it, run that repo's `scripts/pack-nrplugin.sh <this repo>/shared/package/plugins`:
  it builds the plugin **without the vIFF API key** and checks the DLL holds none, because this package is
  public and a key in a DLL can be read back out. Never pack a build that read a `.env` key.
  Controllers given the key set it in NeoRadar with `.cdm apikey`. The C# client loads only C#
  plugins, so the old C++ ones (vACDM, CCAMS, RPC, RampAgent, VATCAN) do not load. Tags and lists
  name no other plugin: the old `NeoVSID` tag item and `NeoVACDM` list are gone.
- **Server-dependent tags.** Arrival runway colours (CDG), SID/runway suggestions and route-based
  rules need the server link and the uploaded server dataset.
- **Not converted yet:** vSID procedure priorities and runway preferences.
- **CLI and schemas from `main`.** `NEORADAR_CLI_REF` / `NEORADAR_SCHEMAS_REF` in
  `.github/workflows/release.yml` (and `ref:` in `validate.yml`) pick the branches CI uses. Point
  them at `develop` only to try changes that have not reached `main` yet.

## Secrets used by the workflows

| Name | For |
| --- | --- |
| `LIVE_DATA_APP_ID` (variable), `LIVE_DATA_APP_PRIVATE_KEY` (secret) | Reading the private `data-sectorfiles` repo |
| `NEORADAR_R2_ACCESS_KEY_ID`, `NEORADAR_R2_SECRET_ACCESS_KEY` | An R2 API token with Object Read & Write on the `neoradar-packages` bucket, for uploading the package |
