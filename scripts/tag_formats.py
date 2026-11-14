"""Generate NeoRadar ATM systems from CoFrance's tag formats.

CoFrance (LFXX/Plugins/CoFrance/config/tag_formats.json) defines one tag format per French
radar unit; a CoFrance ASR picks one with PLUGIN:CoFrance:TagFormat. Every format shares the
same tag layout and differs in its rules: priority-ordered conditions (departure/arrival,
airports, flight rules, squawks, runways, route points) that give a flight its tag colour and
track symbol.

Three formats have hand-made NeoRadar ports in shared/package/systems (HAND_MADE). Every other
format becomes systems/cf-<slug>/: the irma system's label rows and ground section, with the
airborne style variants and target symbols generated from the format's rules, in the same
priority order (CoFrance's lowest priority number wins, as NeoRadar's first matching variant does).

Rule conditions become applyWhen expressions over the aircraft:
  isDeparture / isArrival     -> isDeparture / isArrival == "1" (both: origin AND destination listed)
  airports ["LF**", "LFPG"]   -> origin (departures), destination (arrivals), either (neither flag);
                                 a trailing * is a prefix match
  isIFR / isVFR               -> flightRule contains I / V
  squawk ["123*", "1270"]     -> squawk, prefix or exact
  arrival_runways [...]       -> arrRunway or suggestedArrRunway (both come from the server)
  points [...]                -> the route's waypoints hold one of them (server-parsed)
  flightstate [...]           -> applyToAttentionStates
Style: foreground_color colours the tag text, the leader line, the symbol, the trail and the
speed vector; track_symbol picks a cofrance/* shape. `filtered` and background_color have no
NeoRadar counterpart here and are left out.
"""
from __future__ import annotations

import copy
import json
import re
import shutil
from pathlib import Path

# CoFrance tag format -> hand-made system in shared/package/systems.
# "default" has no rules: CoFrance draws its base look (state colours, CoFrance track symbols),
# which is what the shared default system is.
HAND_MADE = {"IRMA": "irma", "Paris-CDG": "cdg", "Nice": "nce", "default": "default"}
TEMPLATE_SYSTEM = "irma"

FLIGHT_STATES = {
    "assumed": "kAssumed",
    "transferredout": "kOutgoingTransfer",
    "transferredin": "kIncomingTransfer",
    "notified": "kNotified",
    "unconcerned": "kUnconcerned",
    "concerned": "kConcerned",
    "intruder": "kIntruder",
}

# Track symbols, drawn in plotColor (design units are logical pixels, +y down).
SHAPES = {
    "cofrance/circle": {"elements": [{"circle": {"radius": 4}}]},
    "cofrance/square": {"elements": [{"rect": {"size": [8, 8]}}]},
    "cofrance/triangle": {"elements": [{"polygon": [[0, -4.5], [4.5, 3.5], [-4.5, 3.5]]}]},
    "cofrance/invertedtriangle": {"elements": [{"polygon": [[0, 4.5], [4.5, -3.5], [-4.5, -3.5]]}]},
    "cofrance/diamond": {"elements": [{"polygon": [[0, -5], [5, 0], [0, 5], [-5, 0]]}]},
    # Filled forms: only axis-aligned rects fill in the client, so the others nest a second outline.
    "cofrance/circle-filled": {"elements": [{"circle": {"radius": 4}}, {"circle": {"radius": 2.5}}, {"circle": {"radius": 1}}]},
    "cofrance/square-filled": {"elements": [{"rect": {"size": [8, 8]}, "fill": True}]},
    "cofrance/triangle-filled": {"elements": [{"polygon": [[0, -4.5], [4.5, 3.5], [-4.5, 3.5]]}, {"polygon": [[0, -2], [2, 2], [-2, 2]]}]},
    "cofrance/invertedtriangle-filled": {"elements": [{"polygon": [[0, 4.5], [4.5, -3.5], [-4.5, -3.5]]}, {"polygon": [[0, 2], [2, -2], [-2, -2]]}]},
    "cofrance/diamond-filled": {"elements": [{"polygon": [[0, -5], [5, 0], [0, 5], [-5, 0]]}, {"polygon": [[0, -2.5], [2.5, 0], [0, 2.5], [-2.5, 0]]}]},
    "cofrance/trail-dot": {"elements": [{"rect": {"size": [2, 2]}, "fill": True}]},
    "cofrance/trail-square": {"elements": [{"rect": {"size": [3, 3]}}]},
}
for _shape in SHAPES.values():
    _shape.setdefault("pixelSnap", True)
    _shape.setdefault("rotateWithHeading", False)


def slug(text: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


def system_name(fmt: str) -> str:
    return HAND_MADE.get(fmt) or f"cf-{slug(fmt)}"


def hex_color(value) -> list[int] | None:
    if not isinstance(value, str):
        return None
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", value.strip())
    if not m:
        return None
    h = m.group(1)
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def _match(key: str, patterns: list[str]):
    alts = []
    for p in patterns:
        p = str(p).strip().upper()
        if not p:
            continue
        if "*" in p:
            prefix = p.split("*", 1)[0]
            if not prefix:
                return None  # "*" matches everything: no condition
            alts.append(["beginsWith", key, prefix])
        else:
            alts.append(["==", key, p])
    if not alts:
        return None
    return alts[0] if len(alts) == 1 else ["OR", alts]


def _and(terms):
    terms = [t for t in terms if t]
    if not terms:
        return None
    return terms[0] if len(terms) == 1 else ["AND", terms]


class UnsupportedCondition(Exception):
    pass


def condition(c: dict):
    """(applyWhen expression or None, attention states or None) for a rule's conditions."""
    known = {"isDeparture", "isArrival", "isIFR", "isVFR", "airports", "squawk", "arrival_runways", "points", "flightstate"}
    unknown = set(c) - known
    if unknown:
        raise UnsupportedCondition(", ".join(sorted(unknown)))
    terms = []
    dep, arr = c.get("isDeparture"), c.get("isArrival")
    if dep is True and arr is not True:
        terms.append(["==", "isDeparture", "1"])
    elif dep is False:
        terms.append(["!=", "isDeparture", "1"])
    if arr is True and dep is not True:
        terms.append(["==", "isArrival", "1"])
    elif arr is False:
        terms.append(["!=", "isArrival", "1"])
    for key, letter in (("isIFR", "I"), ("isVFR", "V")):
        if c.get(key) is True:
            terms.append(["contains", "flightRule", letter])
        elif c.get(key) is False:
            terms.append(["NOT", [["contains", "flightRule", letter]]])
    if c.get("airports"):
        origin, dest = _match("origin", c["airports"]), _match("destination", c["airports"])
        if origin:
            if dep is True and arr is True:
                terms.append(_and([origin, dest]))
            elif dep is True:
                terms.append(origin)
            elif arr is True:
                terms.append(dest)
            else:
                terms.append(["OR", [origin, dest]])
    if c.get("squawk"):
        terms.append(_match("squawk", c["squawk"]))
    if c.get("arrival_runways"):
        alts = []
        for r in c["arrival_runways"]:
            alts += [["==", "arrRunway", str(r).upper()], ["==", "suggestedArrRunway", str(r).upper()]]
        terms.append(["OR", alts])
    if c.get("points"):
        pts = [["has", "waypoints", str(p).upper()] for p in c["points"]]
        terms.append(pts[0] if len(pts) == 1 else ["OR", pts])
    states = None
    if c.get("flightstate"):
        states = []
        for s in c["flightstate"]:
            if str(s).lower() not in FLIGHT_STATES:
                raise UnsupportedCondition(f"flightstate {s}")
            states.append(FLIGHT_STATES[str(s).lower()])
    return _and(terms), states


def _luminance(rgb: list[int]) -> float:
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def _template_style(labels: dict) -> dict:
    """The irma catch-all variant's look (font, detailed background) without its colours."""
    variants = labels["airborne"]["styleVariants"]
    base = next((v for v in reversed(variants) if not any(k.startswith("apply") for k in v)), variants[-1])
    return {k: copy.deepcopy(v) for k, v in base.items() if k not in ("description", "textColor", "leaderLineColor", "textColorForState")}


def _template_target(targets: dict) -> dict:
    keep = ("historyTrailsSkipSteps",)
    base = targets["airborneSymbology"][-1]
    return {k: copy.deepcopy(base[k]) for k in keep if k in base}


def generate(tag_formats_path: Path, systems_dir: Path, wanted: set[str] | None = None):
    """Writes systems/cf-*/ and the cofrance/* shapes. Returns ({format: system}, [warnings])."""
    warnings: list[str] = []
    formats = json.loads(tag_formats_path.read_text(encoding="utf-8-sig"))["tag_formats"]
    template = systems_dir / TEMPLATE_SYSTEM
    labels_tpl = json.loads((template / "labels.json").read_text(encoding="utf-8"))
    targets_tpl = json.loads((template / "targets.json").read_text(encoding="utf-8"))
    style_tpl, target_tpl = _template_style(labels_tpl), _template_target(targets_tpl)
    catch_all_label = copy.deepcopy(labels_tpl["airborne"]["styleVariants"][-1])
    catch_all_target = copy.deepcopy(targets_tpl["airborneSymbology"][-1])

    mapping: dict[str, str] = {}
    for fmt in formats:
        name = fmt["name"]
        if name in HAND_MADE:
            mapping[name] = HAND_MADE[name]
            continue
        if wanted is not None and name not in wanted:
            continue
        rules = sorted(enumerate(fmt.get("rules", [])), key=lambda ir: (ir[1].get("priority", 99), ir[0]))
        label_variants, target_variants, has_catch_all = [], [], False
        for _, rule in rules:
            try:
                expr, states = condition(rule.get("conditions") or {})
            except UnsupportedCondition as exc:
                warnings.append(f"tag format {name}: rule {rule.get('name')!r} skipped, unsupported condition {exc}")
                continue
            style = rule.get("style") or {}
            fg = hex_color(style.get("foreground_color")) or [255, 255, 255]
            selector = {}
            if expr:
                selector["applyWhen"] = expr
            if states:
                selector["applyToAttentionStates"] = states
            if not selector:
                has_catch_all = True
            label = {"description": f"{name} {rule.get('name', '')}".strip(), **selector, **copy.deepcopy(style_tpl)}
            label["textColor"] = fg
            label["leaderLineColor"] = fg
            if _luminance(fg) >= 60:
                label.pop("detailedTextColor", None)
            label_variants.append(label)
            symbol = str(style.get("track_symbol") or "circle").lower()
            shape = f"cofrance/{symbol}{'-filled' if style.get('track_symbol_fill') else ''}"
            if shape not in SHAPES:
                warnings.append(f"tag format {name}: track symbol {symbol!r} unknown, drawn as a circle")
                shape = "cofrance/circle"
            trail = "cofrance/trail-square" if "square" in str(style.get("history_trail_symbol", "")).lower() else "cofrance/trail-dot"
            target_variants.append({
                "description": label["description"],
                **copy.deepcopy(selector),
                "plotShape": shape,
                "plotColor": fg,
                "historyTrailShape": {"shape": trail, "color": fg},
                "speedVectorColor": fg,
                "rotatePlotWithHeading": False,
                **copy.deepcopy(target_tpl),
            })
            if not selector:
                break  # nothing after a catch-all can be reached
        if not has_catch_all:
            label_variants.append(copy.deepcopy(catch_all_label))
            target_variants.append(copy.deepcopy(catch_all_target))

        out = systems_dir / system_name(name)
        if out.exists():
            shutil.rmtree(out)
        shutil.copytree(template, out)
        labels = copy.deepcopy(labels_tpl)
        labels["airborne"]["styleVariants"] = label_variants
        targets = copy.deepcopy(targets_tpl)
        targets["airborneSymbology"] = target_variants
        (out / "labels.json").write_text(json.dumps(labels, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (out / "targets.json").write_text(json.dumps(targets, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        mapping[name] = system_name(name)

    shapes_path = systems_dir / "shapes.json"
    shapes = json.loads(shapes_path.read_text(encoding="utf-8")) if shapes_path.exists() else {"shapes": {}}
    shapes.setdefault("shapes", {}).update(copy.deepcopy(SHAPES))
    shapes_path.write_text(json.dumps(shapes, indent=2) + "\n", encoding="utf-8")
    return mapping, warnings
