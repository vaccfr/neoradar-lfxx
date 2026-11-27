#!/usr/bin/env python3
"""Build the French vACC NeoRadar package environments.

    python scripts/build.py assemble --source <French vACC tree> [--only LFBB,LFMM]
    neoradar-cli convert build/<ID> <<< y            (per package)
    python scripts/build.py finalize [--only ...]
    neoradar-cli distribute build/<ID> --new-version <v> [--publish]

The source tree is a checkout of vaccfr/Sector-Files with the AIRAC data GNG
publishes laid over it, the layout the Controller Pack Installer produces:

    <FIR>/ASR/**.asr, <FIR>/Settings/LoginProfiles.txt, <FIR>/ICAO/*.txt
    LFXX/Sectors/<FIR>.sct + .ese, LFXX/Sectors/current_airac.txt
    LFXX/Alias/alias.txt, LFXX/Plugins/CoFrance/maps/

`assemble` writes one neoradar-cli package environment per entry of packages.json
under build/<ID>/ (always from scratch), applies diffs/<ID>/*.patch and
diffs/common/*.patch, and converts the CoFrance maps. Centre displays (packages.json
`excludeAsrs`) are left out: the package serves approach, tower and ground. `finalize`
runs after neoradar-cli convert: it gives the converted profiles their ATM system,
altitude filter and CoFrance map items, and prunes manifest layers whose dataset is absent.

The ATM systems are static, hand-maintained files in shared/package/systems: `cdg` for the
Paris-CDG approach, `orly` for the Paris-Orly approach (neoIRMA's tags with CoFrance's Paris-Orly
letters and colours), `neoirma` for every other approach and for the ground displays.

Standard library only.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aviso  # noqa: E402
import cofrance  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SHARED = REPO / "shared"
SCHEMA_URL = "https://raw.githubusercontent.com/neoradar-project/schemas/refs/heads/main/package/manifest.schema.json"

# The sector-file layers neoradar-cli writes, in draw order, with the LFXX look.
SECTOR_LAYERS = [
    {"name": "region", "type": "geojson", "source": "region"},
    {"name": "artcc", "type": "geojson", "source": "artcc", "defaultStyle": {"lineStyle": {"color": [89, 89, 89], "width": 1, "opacity": 1, "dashArray": [2, 1]}}},
    {"name": "ARTCC High", "type": "geojson", "source": "artccHigh", "defaultStyle": {"lineStyle": {"color": [200, 200, 200], "width": 1, "opacity": 1, "dashArray": [2, 1]}}},
    {"name": "ARTCC Low", "type": "geojson", "source": "artccLow", "defaultStyle": {"lineStyle": {"color": [89, 89, 89], "width": 1, "opacity": 1, "dashArray": [2, 1]}}},
    {"name": "Low Airway", "type": "geojson", "source": "lowAirway", "defaultStyle": {"lineStyle": {"color": [83, 94, 78], "width": 1, "opacity": 1}}},
    {"name": "High Airway", "type": "geojson", "source": "highAirway", "defaultStyle": {"lineStyle": {"color": [83, 94, 78], "width": 1, "opacity": 1}}},
    {"name": "sid", "type": "geojson", "source": "sid", "defaultStyle": {"lineStyle": {"color": [83, 94, 78], "width": 1, "opacity": 1}}},
    {"name": "star", "type": "geojson", "source": "star", "defaultStyle": {"lineStyle": {"color": [83, 94, 78], "width": 1, "opacity": 1}}},
    {"name": "geo", "type": "geojson", "source": "geo"},
    {"name": "fix", "type": "geojson", "source": "fix", "hasLabels": True, "defaultStyle": {"pointStyle": {"type": "circle", "size": 3, "fillColor": [83, 94, 78], "fillOpacity": 1, "strokeOpacity": 1, "strokeWidth": 1}, "textStyle": {"color": [0, 255, 0], "fontSize": 12, "offset": [0, 0]}}},
    {"name": "vor", "type": "geojson", "source": "vor", "hasLabels": True, "defaultStyle": {"pointStyle": {"type": "square", "size": 3, "fillColor": [0, 0, 0], "fillOpacity": 1, "strokeOpacity": 1, "strokeWidth": 1}, "textStyle": {"color": [0, 255, 0], "fontSize": 12, "offset": [0, 0]}}},
    {"name": "ndb", "type": "geojson", "source": "ndb", "hasLabels": True, "defaultStyle": {"pointStyle": {"type": "square", "size": 3, "fillColor": [0, 0, 0], "fillOpacity": 1, "strokeOpacity": 1, "strokeWidth": 1}, "textStyle": {"color": [0, 255, 0], "fontSize": 12, "offset": [0, 0]}}},
    {"name": "airport", "type": "geojson", "source": "airport", "hasLabels": True},
    {"name": "runway", "type": "geojson", "source": "runway", "hasLabels": True, "defaultStyle": {"lineStyle": {"color": [0, 0, 0], "width": 2, "opacity": 1}}},
    {"name": "label", "type": "geojson", "source": "label", "isLabelLayer": True, "defaultStyle": {"textStyle": {"color": [255, 255, 255], "fontSize": 12, "offset": [0, 0]}}},
]

# NeoRadar ATM systems (shared/package/systems/<name>). A CoFrance tag format listed here gets its
# own system; every other CoFrance display and every vSMR (AVISO) display uses neoIRMA, whose ground
# section is the package's one ground look (cdg's and orly's ground point at it).
SYSTEM_FOR_TAG_FORMAT = {"Paris-CDG": "cdg", "Paris-Orly": "orly"}
# AVISOs whose airborne traffic is an approach's: Charles de Gaulle and Le Bourget show the
# Paris-CDG colours and letters around the airfield, Orly the Paris-Orly ones. Their ground look is
# the same (cdg's and orly's are #neoirma).
SYSTEM_FOR_AVISO = {"LFPG": "cdg", "LFPB": "cdg", "LFPO": "orly"}
# AVISOs turned so the airport sits square on the screen (map.orientation, degrees).
AVISO_ORIENTATION = {"LFPG": 356, "LFMN": 135}
DEFAULT_SYSTEM = "neoirma"
FRENCH_TRANSITION_ALTITUDE = 5000
# Displays refresh like a radar: aircraft and trails move once per sweep, the trail dots being the
# previous sweeps (map.sweepIntervalSeconds). Approach radar every 2 s, ground (AVISO) every 1 s.
APPROACH_SWEEP_SECONDS = 2
GROUND_SWEEP_SECONDS = 1


def log(msg: str) -> None:
    print(msg, flush=True)


def warn(msg: str) -> None:
    prefix = "::warning::" if _in_ci() else "WARNING: "
    print(prefix + msg, flush=True)


def _in_ci() -> bool:
    import os

    return os.environ.get("GITHUB_ACTIONS") == "true"


def load_config() -> dict:
    return json.loads((REPO / "packages.json").read_text(encoding="utf-8"))


def select(config: dict, only: str | None) -> list[dict]:
    pkgs = config["packages"]
    if not only:
        return pkgs
    wanted = {s.strip().upper() for s in only.split(",") if s.strip()}
    unknown = wanted - {p["id"] for p in pkgs}
    if unknown:
        sys.exit(f"Unknown package id(s): {', '.join(sorted(unknown))}")
    return [p for p in pkgs if p["id"] in wanted]


def read_text_any(path: Path) -> str:
    """Decodes UTF-8, falling back to Windows-1252, with line endings normalised to LF so a
    patch authored on Windows applies on the Linux runner."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    return text.replace("\r\n", "\n")


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def ese_positions(ese: Path) -> dict[str, str]:
    """Callsign -> position id from the ESE [POSITIONS] section."""
    out, section = {}, None
    for raw in read_text_any(ese).splitlines():
        line = raw.strip()
        if line.startswith("["):
            section = line.upper()
            continue
        if section == "[POSITIONS]" and line and not line.startswith(";"):
            parts = line.split(":")
            if len(parts) > 3 and parts[0] and parts[3]:
                out.setdefault(parts[0].strip(), parts[3].strip())
    return out


def apply_replacements(text: str, target_rel: str, rules: list[dict]) -> str:
    for rule in rules:
        if not fnmatch.fnmatch(target_rel, rule["appliesTo"]):
            continue
        count = text.count(rule["find"])
        if count == 0:
            warn(f"replacement {rule['find']!r} matched nothing in {target_rel}; upstream may have changed wording")
            continue
        text = text.replace(rule["find"], rule["replace"])
    return text


def copy_tree_text(src: Path, dst: Path, suffix: str, exclude: list[str] | None = None) -> tuple[int, list[str]]:
    """Copies every *<suffix> file under src to dst, re-encoded as UTF-8 (the CLI reads UTF-8,
    the French files are partly Windows-1252). A file whose path relative to src matches one of
    the `exclude` globs is skipped. Returns (files copied, relative paths skipped)."""
    n, skipped = 0, []
    for f in sorted(src.rglob(f"*{suffix}")):
        rel = f.relative_to(src).as_posix()
        if any(fnmatch.fnmatch(rel, pattern) for pattern in exclude or []):
            skipped.append(rel)
            continue
        target = dst / f.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(read_text_any(f), encoding="utf-8", newline="\n")
        n += 1
    return n, skipped


def drop_login_profiles(text: str, facilities: set[str]) -> tuple[str, list[str]]:
    """Removes the LoginProfiles.txt profiles whose facility (PROFILE:<callsign>:<range>:<facility>)
    is in `facilities`, with the ATIS lines that follow them. Returns (text, dropped callsigns)."""
    if not facilities:
        return text, []
    out, dropped, skipping = [], [], False
    for line in text.split("\n"):
        if line.startswith("PROFILE:"):
            fields = line.split(":")
            skipping = len(fields) > 3 and fields[3].strip() in facilities
            if skipping:
                dropped.append(fields[1])
                continue
        elif line.startswith("PROFILE"):
            skipping = False
        if not skipping:
            out.append(line)
    return "\n".join(out), dropped


def drop_unidentified_positions(ese: Path) -> list[str]:
    """Removes [POSITIONS] lines whose identifier field (the 4th) is blank and returns their callsigns.

    Such a position cannot own airspace, and neoradar-cli turns the blank identifier into a sector
    with an empty id that the first such position "owns": the client reads a position's identifier
    as sectors[0] and throws on the empty one (EBOS_APP, LFBI_APP in GNG 2611). Works on bytes so
    the GNG file's encoding and line endings are kept as they are."""
    raw = ese.read_bytes()
    out, dropped, section = [], [], b""
    for line in raw.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith(b"["):
            section = stripped.upper()
        elif section == b"[POSITIONS]" and stripped and not stripped.startswith(b";"):
            fields = stripped.split(b":")
            if len(fields) > 3 and not fields[3].strip():
                dropped.append(fields[0].decode("latin-1"))
                continue
        out.append(line)
    if dropped:
        ese.write_bytes(b"".join(out))
    return dropped


def apply_diffs(env: Path, pkg_id: str) -> None:
    patches = sorted((REPO / "diffs" / "common").glob("*.patch")) + sorted((REPO / "diffs" / pkg_id).glob("*.patch"))
    for patch in patches:
        log(f"  applying {patch.relative_to(REPO)}")
        subprocess.run(
            ["git", "apply", "--whitespace=fix", f"--directory={env.relative_to(REPO).as_posix()}", str(patch)],
            cwd=REPO,
            check=True,
        )


def assemble(pkg: dict, config: dict, source: Path, build: Path) -> None:
    pid = pkg["id"]
    env = build / pid
    log(f"== assemble {pid} -> {env}")
    if env.exists():
        shutil.rmtree(env)
    env.mkdir(parents=True)
    rules = json.loads((REPO / "transforms" / "replacements.json").read_text(encoding="utf-8"))["rules"]
    sectors = source / "LFXX" / "Sectors"
    airac_file = sectors / "current_airac.txt"
    airac = airac_file.read_text(encoding="utf-8").strip() if airac_file.exists() else ""
    if not re.fullmatch(r"\d{4}", airac):
        sys.exit(f"{airac_file}: expected a 4-digit AIRAC cycle, got {airac!r}")

    # config.json: packages.json's publish settings as neoradar-cli distribute reads them, with the
    # package's own path (prefix + namespace) in the bucket and under the public URL
    pub = config["publish"]
    slug = pkg["namespace"]
    publish = {k: v for k, v in pub.items() if k not in ("$comment", "s3PathPrefix", "baseUrlPrefix")}
    publish["s3Path"] = pub.get("s3PathPrefix", "") + slug
    publish["baseUrl"] = pub["baseUrlPrefix"] + slug
    (env / "config.json").write_text(json.dumps({
        "sectorFileFromGNG": True,
        "publish": publish,
    }, indent=2) + "\n", encoding="utf-8")

    # sector_files/<ID>.sct + .ese
    (env / "sector_files").mkdir()
    for ext in ("sct", "ese"):
        src = sectors / f"{pkg['sectorFile']}.{ext}"
        if not src.is_file():
            sys.exit(f"Missing sector file {src}")
        for alias in pkg.get("sectorFileAliases", []):
            other = sectors / f"{alias}.{ext}"
            if other.is_file() and md5(other) != md5(src):
                warn(f"{other.name} differs from {src.name}; {pid} is built from {src.name} only")
        shutil.copyfile(src, env / "sector_files" / f"{pid}.{ext}")

    # ASRs: one FIR straight in, several FIRs one folder each
    asr_root = env / "ASRs"
    count, left_out = 0, []
    for fir in pkg["firs"]:
        target = asr_root if len(pkg["firs"]) == 1 else asr_root / fir
        copied, skipped = copy_tree_text(source / fir / "ASR", target, ".asr", pkg.get("excludeAsrs"))
        count += copied
        left_out += [f"{fir}/{rel}" for rel in skipped]
    log(f"  {count} ASR files; left out by excludeAsrs: {', '.join(left_out) or 'none'}")

    # euroscope_data: alias + one LoginProfiles.txt, the FIRs' files concatenated so the CLI
    # groups every profile by callsign prefix (the first FIR wins a duplicated callsign)
    ed = env / "euroscope_data"
    ed.mkdir()
    alias = source / "LFXX" / "Alias" / "alias.txt"
    (ed / "Alias.txt").write_text(read_text_any(alias), encoding="utf-8", newline="\n")
    rel = "euroscope_data/LoginProfiles.txt"
    chunks, dropped_logins = [], []
    excluded_facilities = {str(f) for f in pkg.get("excludeLoginFacilities", [])}
    for fir in pkg["firs"]:
        lp = source / fir / "Settings" / "LoginProfiles.txt"
        if not lp.is_file():
            warn(f"{lp} missing")
            continue
        text = apply_replacements(read_text_any(lp), f"{rel} ({fir})", rules)
        text, dropped = drop_login_profiles(text, excluded_facilities)
        dropped_logins += dropped
        chunks.append(text.rstrip("\n"))
    (env / rel).write_text("\n".join(chunks) + "\n", encoding="utf-8", newline="\n")
    if excluded_facilities:
        log(f"  {len(dropped_logins)} login profiles left out by excludeLoginFacilities ({', '.join(sorted(excluded_facilities))})")

    # icao_data
    data_folder = pkg.get("dataFolder", pkg["firs"][0])
    icao = env / "icao_data"
    icao.mkdir()
    for name in ("ICAO_Aircraft.txt", "ICAO_Airlines.txt", "ICAO_Airports.txt"):
        src = source / data_folder / "ICAO" / name
        if not src.is_file():
            src = source / "LFXX" / "ICAO" / name
        shutil.copyfile(src, icao / name)
    shutil.copyfile(SHARED / "icao_data" / "recat.json", icao / "recat.json")

    # package/: shared content + manifest
    package = env / "package"
    shutil.copytree(SHARED / "package", package, ignore=shutil.ignore_patterns(".gitkeep", ".DS_Store"))
    (package / "datasets").mkdir(exist_ok=True)

    plugin_version = None
    version_file = source / "LFXX" / "Plugins" / "CoFrance" / "version.json"
    if version_file.exists():
        plugin_version = json.loads(version_file.read_text(encoding="utf-8-sig")).get("plugin_version")
    maps_root = source / "LFXX" / "Plugins" / "CoFrance" / "maps"
    positions = ese_positions(env / "sector_files" / f"{pid}.ese")
    layers, uuids, report = cofrance.convert(
        maps_root, config.get("sharedCoFranceMaps", []) + pkg["firs"], package / "datasets" / "maps", positions, plugin_version
    )
    log(f"  CoFrance: {report.layers} layers, {report.items} items, {report.drawings} drawings")
    for w in report.warnings:
        warn(f"CoFrance {pid}: {w}")
    if report.unresolved_sectors:
        warn(f"CoFrance {pid}: sectors with no position in {pid}.ese (their sector-ownership rules never show): "
             + ", ".join(sorted(report.unresolved_sectors)))

    # The vSMR fork's AVISO files: one layer per airport, what the AVISO profiles draw.
    vsmr_data = source / "LFXX" / "Plugins" / "vSMR" / "vSMR_Data"
    inventory = vsmr_data / "AVISO-INVENTORY.json"
    aviso_release = json.loads(inventory.read_text(encoding="utf-8-sig")).get("release") if inventory.is_file() else None
    palettes = {}
    for asr in (env / "ASRs").rglob("*.asr"):
        meta = parse_asr(asr)
        palette = meta["plugin"].get(("vSMR", "AvisoColorPalette"), "").strip()
        if meta.get("DisplayTypeName", "").lower().startswith("smr") and palette:
            palettes[aviso_airport(asr, meta)] = palette
    aviso_layers, aviso_profiles, aviso_report = aviso.convert(vsmr_data / "AVISO", package / "datasets" / "maps", aviso_release, palettes)
    log(f"  AVISO: {aviso_report.layers} airports, {aviso_report.items} items, {aviso_report.drawings} drawings")
    for w in aviso_report.warnings:
        warn(f"{pid}: {w}")
    layers = layers + aviso_layers

    fonts = sorted(p.name for p in (package / "fonts").glob("*.ttf"))
    # Plugins ship as .nrplugin archives in shared/package/plugins; a bare .dll in a package is refused.
    plugins = sorted(f"plugins/{p.name}" for p in (package / "plugins").glob("*.nrplugin"))
    log(f"  plugins: {', '.join(plugins) or 'none'}")
    manifest = {
        "$schema": SCHEMA_URL,
        "id": pid,
        "name": pkg["name"],
        "version": airac,
        "description": f"{pkg['description']}, AIRAC {airac}",
        "namespace": pkg["namespace"],
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "mapLayers": SECTOR_LAYERS + layers,
        "fonts": [{"alias": Path(f).stem, "src": f} for f in fonts],
        "plugins": plugins,
    }
    (package / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (env / "build-info.json").write_text(json.dumps({
        "id": pid,
        "airac": airac,
        "sectorFile": f"{pkg['sectorFile']}.sct",
        "sectorFileMd5": md5(env / "sector_files" / f"{pid}.sct"),
        "cofrancePluginVersion": plugin_version,
        "cofranceItems": sorted(uuids),
        "avisoItems": aviso_profiles,
    }, indent=2) + "\n", encoding="utf-8")

    apply_diffs(env, pid)
    dropped = drop_unidentified_positions(env / "sector_files" / f"{pid}.ese")
    if dropped:
        warn(f"{pid}: ESE positions with no identifier, dropped (they cannot own airspace and break the client): {', '.join(dropped)}")


def parse_asr(path: Path) -> dict:
    out = {"plugin": {}}
    for line in read_text_any(path).splitlines():
        if line.startswith("PLUGIN:"):
            parts = line.split(":", 3)
            if len(parts) == 4:
                out["plugin"][(parts[1], parts[2])] = parts[3].strip()
        elif ":" in line:
            key, _, value = line.partition(":")
            out.setdefault(key.strip(), value.strip())
    return out


def aviso_airport(asr: Path, meta: dict) -> str:
    """The airport an AVISO ASR shows: PLUGIN:vSMR:Airport, unless the file is named for another
    one ("LFAC Calais AVISO" pointing vSMR at LFAQ, a copy-paste slip upstream). The name is what
    the controller picks the display by, so it wins."""
    icao = meta["plugin"].get(("vSMR", "Airport"), "").strip().upper()
    named = re.match(r"^([A-Z]{4}) .*AVISO$", asr.stem.upper())
    return named.group(1) if named else icao


def layer_items(datasets: Path, source: str) -> list[dict]:
    path = datasets / f"{source}.geojson"
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("items", [])


def aviso_items(sector_items: dict[str, list[dict]], icao: str) -> list[str]:
    """The sector-file items an AVISO of `icao` draws. The major airports have dedicated ones:
    the '<ICAO> AVISO' region(s) and the '<ICAO> Groundlayout AVISO' geo (and variants such as
    '... Gates'). The others only have their '<ICAO> Groundlayout <name>' geo, drawn with the
    airport's runways. An airport with no ground layout at all gets its runways alone.
    Returns (uuids, kind) where kind is 'aviso', 'layout' or 'runways'."""
    if not re.fullmatch(r"[A-Z]{4}", icao):
        return [], ""

    def named(source: str, prefix: str) -> list[str]:
        return [i["uuid"] for i in sector_items.get(source, []) if i["name"].upper().startswith(prefix)]

    dedicated = named("region", f"{icao} AVISO") + named("geo", f"{icao} GROUNDLAYOUT AVISO")
    if dedicated:
        return dedicated, "aviso"
    runways = named("runway", f"{icao}-")
    layout = named("geo", f"{icao} GROUNDLAYOUT")
    if layout:
        return layout + runways, "layout"
    return runways, "runways"


def finalize(pkg: dict, build: Path) -> None:
    pid = pkg["id"]
    env = build / pid
    log(f"== finalize {pid}")
    info = json.loads((env / "build-info.json").read_text(encoding="utf-8"))
    known = set(info["cofranceItems"])
    aviso_profiles: dict[str, list[str]] = info.get("avisoItems", {})
    package = env / "package"
    profiles = package / "profiles"

    sector_items = {s: layer_items(package / "datasets", s) for s in ("region", "geo", "runway")}
    missing_maps: set[str] = set()
    no_aviso: set[str] = set()
    runways_only: set[str] = set()
    from_sector_file: set[str] = set()
    replaced_items: set[str] = set()
    dangling: dict[str, list[str]] = {}
    all_items = {
        item["uuid"]
        for layer in (package / "datasets").rglob("*.geojson")
        for item in json.loads(layer.read_text(encoding="utf-8")).get("items", [])
    }
    touched = 0
    systems_used: dict[str, int] = {}
    for asr in sorted((env / "ASRs").rglob("*.asr")):
        rel = asr.relative_to(env / "ASRs").with_suffix(".stp")
        stp = profiles / rel
        if not stp.is_file():
            warn(f"{pid}: no converted profile for {asr.relative_to(env)}")
            continue
        meta = parse_asr(asr)
        profile = json.loads(stp.read_text(encoding="utf-8"))
        if meta.get("DisplayTypeName", "").lower().startswith("cofrance"):
            fmt = meta["plugin"].get(("CoFrance", "TagFormat"), "")
            profile["atmSystem"] = SYSTEM_FOR_TAG_FORMAT.get(fmt, DEFAULT_SYSTEM)
            profile["map"]["sweepIntervalSeconds"] = APPROACH_SWEEP_SECONDS
            radar = profile.setdefault("radarData", {})
            radar["transitionAltitude"] = FRENCH_TRANSITION_ALTITUDE
            for key, field in (("UpperAlt", "upperFilterValue"), ("LowerAlt", "lowerFilterValue")):
                enabled = meta["plugin"].get(("CoFrance", f"{key}Enabled"), "0") == "1"
                value = meta["plugin"].get(("CoFrance", key))
                if enabled and value and value.lstrip("-").isdigit():
                    radar[field] = int(value)
            items = profile["map"].setdefault("items", [])
            present = {i["uuid"] for i in items}
            for ref in filter(None, (r.strip() for r in meta["plugin"].get(("CoFrance", "EnabledMaps"), "").split(","))):
                uuid = cofrance.map_uuid(ref)
                if uuid not in known:
                    missing_maps.add(ref)
                    continue
                if uuid not in present:
                    items.append({"showLabel": False, "uuid": uuid})
                    present.add(uuid)
        else:
            # vSMR displays (the AVISOs) and anything else: neoIRMA, whose ground section is the
            # AVISO look. Named explicitly: with no atmSystem the client takes the first system
            # alphabetically, cdg.
            profile["atmSystem"] = DEFAULT_SYSTEM
        if meta.get("DisplayTypeName", "").lower().startswith("smr"):
            # The French AVISO ASRs carry no map content (Sector-Files' maintenance script strips it):
            # the vSMR fork draws the AVISO of PLUGIN:vSMR:Airport itself, from its own AVISO file.
            # An empty item list would draw every layer, so the profile lists exactly that
            # airport's AVISO layer (scripts/aviso.py), and nothing else.
            icao = aviso_airport(asr, meta)
            set_icao = meta["plugin"].get(("vSMR", "Airport"), "").strip().upper()
            if set_icao != icao:
                warn(f"{pid}: {asr.name} sets vSMR:Airport:{set_icao or '(none)'}; using {icao} from its name")
            profile["atmSystem"] = SYSTEM_FOR_AVISO.get(icao, DEFAULT_SYSTEM)
            profile["map"]["sweepIntervalSeconds"] = GROUND_SWEEP_SECONDS
            if icao in AVISO_ORIENTATION:
                profile["map"]["orientation"] = AVISO_ORIENTATION[icao]
            if profile["map"].get("items"):
                replaced_items.add(asr.relative_to(env / "ASRs").as_posix())
            if aviso_profiles.get(icao):
                profile["map"]["items"] = [{"showLabel": False, "uuid": u} for u in aviso_profiles[icao]]
            else:
                # No vSMR AVISO file for this airport: the sector file's AVISO items, as before.
                uuids, kind = aviso_items(sector_items, icao)
                profile["map"]["items"] = [{"showLabel": False, "uuid": u} for u in uuids]
                if uuids:
                    from_sector_file.add(icao)
                    if kind == "runways":
                        runways_only.add(icao)
                else:
                    no_aviso.add(f"{asr.relative_to(env / 'ASRs').as_posix()} ({icao or 'no vSMR airport'})")
        systems_used[profile["atmSystem"]] = systems_used.get(profile["atmSystem"], 0) + 1
        # An ASR entry naming an object the sector file no longer has (a renumbered runway, a
        # withdrawn navaid) converts to an item no layer holds: EuroScope ignores such a line, so
        # drop the row and report it, upstream's ASR is what needs the fix.
        kept_items = []
        for item in profile["map"].get("items", []):
            if item["uuid"] in all_items:
                kept_items.append(item)
            else:
                dangling.setdefault(asr.relative_to(env / "ASRs").as_posix(), []).append(item["uuid"])
        profile["map"]["items"] = kept_items
        stp.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
        touched += 1
    log(f"  {touched} profiles finalized: " + ", ".join(f"{n} {name}" for name, n in sorted(systems_used.items())))
    absent = sorted(name for name in systems_used if not (package / "systems" / name).is_dir())
    if absent:
        sys.exit(f"{pid}: profiles use systems that shared/package/systems does not have: {', '.join(absent)}")
    if from_sector_file:
        warn(f"{pid}: AVISO displays with no vSMR AVISO file, drawn from the sector file's AVISO items instead (add LFXX/Plugins/vSMR/vSMR_Data/AVISO/<ICAO>.geojson in Sector-Files): {', '.join(sorted(from_sector_file))}")
    if replaced_items:
        warn(f"{pid}: AVISO ASRs listing map items of their own, replaced by the airport's AVISO (fix the ASR in Sector-Files): {', '.join(sorted(replaced_items))}")
    if runways_only:
        warn(f"{pid}: AVISO displays drawing runways only, the sector file has no ground layout for: {', '.join(sorted(runways_only))}")
    if no_aviso:
        warn(f"{pid}: AVISO displays whose airport has no AVISO or ground layout items in the sector file, left showing every layer: {', '.join(sorted(no_aviso))}")
    for name, uuids in sorted(dangling.items()):
        warn(f"{pid}: {name} names {len(uuids)} object(s) the sector file does not have, dropped: {', '.join(sorted(set(uuids)))}")
    if missing_maps:
        warn(f"{pid}: CoFrance maps named by ASRs but absent from the CoFrance maps folder: {', '.join(sorted(missing_maps))}")

    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    kept = []
    for layer in manifest["mapLayers"]:
        if (package / "datasets" / f"{layer['source']}.geojson").is_file():
            kept.append(layer)
        else:
            log(f"  manifest: dropping layer {layer['source']!r}, no dataset")
    manifest["mapLayers"] = kept
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    for stray in package.rglob("neoradar-cli.log"):
        stray.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("assemble", help="write build/<ID> package environments from the source tree")
    a.add_argument("--source", required=True, type=Path)
    f = sub.add_parser("finalize", help="post-process build/<ID> after neoradar-cli convert")
    for p in (a, f):
        p.add_argument("--only", help="comma-separated package ids (default: all)")
        p.add_argument("--build", type=Path, default=REPO / "build")
    sub.add_parser("ids", help="print the package ids as a JSON array (for CI matrices)")
    args = parser.parse_args()

    config = load_config()
    if args.command == "ids":
        print(json.dumps([p["id"] for p in config["packages"]]))
        return 0
    build = args.build.resolve()
    for pkg in select(config, args.only):
        if args.command == "assemble":
            assemble(pkg, config, args.source.resolve(), build)
        else:
            finalize(pkg, build)
    return 0


if __name__ == "__main__":
    sys.exit(main())
