"""Convert the French vSMR fork's AVISO files into NeoRadar map layers.

The AVISO displays (vSMR radar displays, `PLUGIN:vSMR:Airport:<ICAO>`) draw what the vSMR fork
ships in LFXX/Plugins/vSMR/vSMR_Data/AVISO/<ICAO>.geojson: the airport's surfaces, guidance lines,
labels and, at LFPG, the runway-configuration arrows. Those files hold more than the sector file
(aprons, buildings, helipads, extra gates), so the AVISO profiles draw them rather than the
sector file's AVISO items.

One airport becomes one layer (datasets/maps/aviso-<icao>.geojson) whose items are what an
AVISO profile lists:
  <ICAO> background      the palette's background colour under the whole airport, drawn first
  <ICAO> ground layout   every surface and line, in the file's paint order
  <ICAO> <label kind>    one item per label category (Gates, Taxiways, TORA...)
  <ICAO> <group>         one item per vSMR group (East Arrows...). A group named for a direction
                         draws only while a runway end facing that way is active, as a drawing
                         showWhen, so it shows only where its item is listed (that AVISO)

Colours are the palette the airport's AVISO ASR picks (PLUGIN:vSMR:AvisoColorPalette, "real" at the
major airports), else the file's default_color_palette ("dark"). Label zoom levels become
minPixelsPerNm (ZOOM_PX_PER_NM).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from cofrance import slug, to_mercator, project

# vSMR label zoom level -> NeoRadar minPixelsPerNm. vSMR's scale is not documented; zoom 7 is
# taken as the AVISO's opening view (no limit) and each level above as twice the scale.
ZOOM_PX_PER_NM = {8: 600, 9: 1200}
BACKGROUND_MARGIN_DEG = 0.3
DIRECTIONS = {"north": 0, "east": 90, "south": 180, "west": 270}


@dataclass
class Report:
    warnings: list[str] = field(default_factory=list)
    layers: int = 0
    items: int = 0
    drawings: int = 0


def color(value) -> list[int] | None:
    if not isinstance(value, str):
        return None
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", value.strip())
    if not m:
        return None
    h = m.group(1)
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def paint_of(style: dict, palette: str) -> dict:
    paint = dict(style.get("paint") or {})
    overrides = (paint.pop("palette-overrides", None) or {}).get(palette) or {}
    paint.update(overrides)
    return paint


def opacity(value) -> float | None:
    return max(0.0, min(1.0, float(value))) if isinstance(value, (int, float)) else None


def clean_name(text: str) -> str:
    """Category names in the files carry a mis-decoded dash ("arrows � green")."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s()/+.-]", " ", text)).strip()


def item_uuid(icao: str, part: str) -> str:
    return f"aviso-{icao.lower()}-{slug(part)}"


def runway_condition(icao: str, direction: str, runways: list[dict]) -> list | None:
    """Any runway end facing `direction` (within 90 degrees) active for arrivals or departures."""
    target = DIRECTIONS[direction]
    ends = []
    for rwy in runways:
        for end, heading in zip(rwy.get("ends", []), rwy.get("headings", [])):
            delta = abs((float(heading) - target + 180) % 360 - 180)
            if delta < 90:
                ends.append(str(end))
    alts = [["has", key, f"{icao}{end}"] for end in sorted(set(ends)) for key in ("arrivalRunways", "departureRunways")]
    if not alts:
        return None
    return alts[0] if len(alts) == 1 else ["OR", alts]


def group_direction(group: dict) -> str | None:
    words = re.findall(r"[a-z]+", f"{group.get('id', '')} {group.get('name', '')}".lower())
    found = [w for w in words if w in DIRECTIONS]
    return found[0] if len(set(found)) == 1 else None


def convert_airport(path: Path, report: Report, palettes: dict[str, str]) -> tuple[str, list[dict], list[dict], list[str]]:
    """Returns (ICAO, items, drawings, uuids the AVISO profile lists)."""
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    meta = data.get("metadata") or {}
    icao = str(meta.get("airport") or path.stem).upper()
    default = str(meta.get("default_color_palette") or "dark")
    palette = palettes.get(icao) or default
    if palette not in (meta.get("color_palettes") or [default]):
        report.warnings.append(f"AVISO {icao}: the ASR asks for palette {palette!r}, the file has {meta.get('color_palettes')}; using {default!r}")
        palette = default
    styles = data.get("styles") or {}
    runways = meta.get("runways") or []

    items: list[dict] = []
    drawings: list[dict] = []
    listed: list[str] = []

    def add_item(part: str, name: str, order: int | None = None, listed_by_profile: bool = True) -> str:
        uuid = item_uuid(icao, part)
        if not any(i["uuid"] == uuid for i in items):
            item = {"uuid": uuid, "name": name}
            if order is not None:
                item["order"] = order
            items.append(item)
            if listed_by_profile:
                listed.append(uuid)
        return uuid

    # Background: the palette's colour well past the airport, so the AVISO reads as in vSMR.
    bg = color(((meta.get("background_colors") or {}).get(palette)))
    bbox = data.get("bbox") or meta.get("bbox")
    if bg and isinstance(bbox, list) and len(bbox) == 4:
        m = BACKGROUND_MARGIN_DEG
        w, s, e, n = bbox[0] - m, bbox[1] - m, bbox[2] + m, bbox[3] + m
        uuid = add_item("background", f"{icao} background", order=0)
        drawings.append({"type": "Feature", "properties": {"uuid": uuid, "type": "AVISO", "fillStyle": {"color": bg}},
                         "geometry": {"type": "Polygon", "coordinates": [project([[w, s], [e, s], [e, n], [w, n], [w, s]])]}})

    groups = {g.get("id"): g for g in data.get("vsmr_groups") or []}
    group_items: dict[str, tuple[str, list | None]] = {}
    for gid, group in groups.items():
        direction = group_direction(group)
        cond = runway_condition(icao, direction, runways) if direction else None
        if direction and cond is None:
            report.warnings.append(f"AVISO {icao}: group {group.get('name')!r} faces {direction} but no runway end does; drawn whenever listed")
        uuid = add_item(f"group-{gid}", f"{icao} {clean_name(str(group.get('name') or gid))}", order=2,
                        listed_by_profile=group.get("visible", True) is not False)
        group_items[gid] = (uuid, cond)

    layout_uuid = None
    for feature in data.get("features") or []:
        props = feature.get("properties") or {}
        geometry = feature.get("geometry")
        if not geometry:
            continue
        style = styles.get(props.get("style_id"))
        if style is None:
            report.warnings.append(f"AVISO {icao}: feature {props.get('name')!r} has no style {props.get('style_id')!r}, skipped")
            continue
        paint = paint_of(style, palette)
        kind = props.get("object_type") or style.get("object_type")
        base: dict = {"type": "AVISO"}
        if props.get("name"):
            base["name"] = str(props["name"])

        group_ids = [g for g in props.get("vsmr_group_ids") or [] if g in group_items]
        if group_ids:
            uuid, cond = group_items[group_ids[0]]
            base["uuid"] = uuid
            if cond:
                base["showWhen"] = cond
        elif kind == "Label":
            category = clean_name(str(props.get("category") or style.get("name") or "Labels"))
            base["uuid"] = add_item(f"labels-{category}", f"{icao} {category}")
        else:
            if layout_uuid is None:
                layout_uuid = add_item("ground-layout", f"{icao} ground layout", order=1)
            base["uuid"] = layout_uuid

        gtype = geometry["type"]
        if kind == "Label":
            text = props.get("text-field") or props.get("name")
            if not text or gtype != "Point":
                continue
            text_style = {}
            if color(paint.get("text-color")):
                text_style["color"] = color(paint.get("text-color"))
            if isinstance(paint.get("text-size"), (int, float)) and paint["text-size"] > 0:
                text_style["fontSize"] = paint["text-size"]
            d = {**base, "text": str(text), "textStyle": text_style}
            zoom = paint.get("zoomLevel")
            if isinstance(zoom, (int, float)) and int(zoom) in ZOOM_PX_PER_NM:
                d["minPixelsPerNm"] = ZOOM_PX_PER_NM[int(zoom)]
            drawings.append({"type": "Feature", "properties": d, "geometry": {"type": "Point", "coordinates": to_mercator(*geometry["coordinates"][:2])}})
            continue

        d = dict(base)
        stroke = color(paint.get("stroke"))
        if stroke:
            line = {"color": stroke}
            if isinstance(paint.get("stroke-width"), (int, float)) and paint["stroke-width"] > 0:
                line["width"] = paint["stroke-width"]
            if opacity(paint.get("stroke-opacity")) is not None:
                line["opacity"] = opacity(paint.get("stroke-opacity"))
            d["lineStyle"] = line
        fill = color(paint.get("fill"))
        if fill and gtype in ("Polygon", "MultiPolygon"):
            fs = {"color": fill}
            if opacity(paint.get("fill-opacity")) is not None:
                fs["opacity"] = opacity(paint.get("fill-opacity"))
            d["fillStyle"] = fs
        if "lineStyle" not in d and "fillStyle" not in d:
            report.warnings.append(f"AVISO {icao}: {gtype} {props.get('name')!r} with no usable paint, skipped")
            continue
        drawings.append({"type": "Feature", "properties": d, "geometry": {"type": gtype, "coordinates": project(geometry["coordinates"])}})

    used = {d["properties"]["uuid"] for d in drawings}
    items = [i for i in items if i["uuid"] in used]
    listed = [u for u in listed if u in used]
    return icao, items, drawings, listed


def convert(aviso_dir: Path, out_dir: Path, release: str | None, palettes: dict[str, str]) -> tuple[list[dict], dict[str, list[str]], Report]:
    """Writes datasets/maps/aviso-<icao>.geojson for every AVISO file, in the palette `palettes`
    names for the airport (its ASR's choice) or the file's default.
    Returns (manifest layer entries, {ICAO: item uuids its AVISO profile lists}, Report)."""
    report = Report()
    layers: list[dict] = []
    profile_items: dict[str, list[str]] = {}
    if not aviso_dir.is_dir():
        report.warnings.append(f"{aviso_dir} missing: AVISO displays fall back to the sector file's AVISO items")
        return layers, profile_items, report
    out_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(aviso_dir.glob("*.geojson")):
        icao, items, drawings, listed = convert_airport(path, report, palettes)
        if not drawings:
            report.warnings.append(f"AVISO {icao}: nothing drawable, no layer")
            continue
        name = f"AVISO {icao}"
        origin = {"kind": "authored", "file": "vSMR AVISO"}
        if release:
            origin["version"] = release
        doc = {"type": "FeatureCollection", "name": name, "origin": origin, "items": items, "features": drawings}
        source = f"maps/aviso-{icao.lower()}"
        (out_dir / f"aviso-{icao.lower()}.geojson").write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
        layers.append({"name": name, "type": "geojson", "source": source, "hasLabels": False, "isLabelLayer": False})
        profile_items[icao] = listed
        report.layers += 1
        report.items += len(items)
        report.drawings += len(drawings)
    return layers, profile_items, report
