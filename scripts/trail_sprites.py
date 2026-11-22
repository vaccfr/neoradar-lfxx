"""Tapered, fading trail sprites for the systems' history trails.

    python scripts/trail_sprites.py

Writes shared/package/images/symbols.png + symbols.json (frames trails/<rrggbb>/t1..t8, one per
trail colour the systems' targets use) and points every airborne variant's historyTrailImages at
its colour's frames. Sprites, because released clients cannot size a trail shape per mark; once
historyTrailShape.scaleRamp is released, the trails can go back to shapes.
"""
import json
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
SYSTEMS = REPO / "shared" / "package" / "systems"
IMAGES = REPO / "shared" / "package" / "images"
FRAME = 8
DIAMETERS = [6, 5.1, 4.3, 3.6, 3.0, 2.5, 2.1, 1.8]  # newest first: the comet narrows behind the plot
ALPHAS = [0.9, 0.75, 0.62, 0.5, 0.4, 0.3, 0.22, 0.15]


def dot(color, diameter, alpha):
    img = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
    c, r = FRAME / 2, diameter / 2
    for y in range(FRAME):
        for x in range(FRAME):
            # Coverage of the pixel by the disc, sampled 4 x 4, for a soft but small dot.
            inside = sum(((x + (i + 0.5) / 4 - c) ** 2 + (y + (j + 0.5) / 4 - c) ** 2) <= r * r for i in range(4) for j in range(4))
            if inside:
                img.putpixel((x, y), (*color, round(255 * alpha * inside / 16)))
    return img


def main():
    targets = {s: json.loads((SYSTEMS / s / "targets.json").read_text(encoding="utf-8")) for s in ("cdg", "neoirma")}
    colors = []
    for doc in targets.values():
        for v in doc["airborneSymbology"]:
            c = (v.get("historyTrailShape") or {}).get("color") or v.get("plotColor")
            if isinstance(c, list) and tuple(c[:3]) not in colors:
                colors.append(tuple(c[:3]))

    atlas = Image.new("RGBA", (FRAME * len(DIAMETERS), FRAME * len(colors)), (0, 0, 0, 0))
    frames = {}
    for row, color in enumerate(colors):
        key = "%02x%02x%02x" % color
        for i, (d, a) in enumerate(zip(DIAMETERS, ALPHAS)):
            atlas.paste(dot(color, d, a), (i * FRAME, row * FRAME))
            frames[f"trails/{key}/t{i + 1}"] = {
                "frame": {"x": i * FRAME, "y": row * FRAME, "w": FRAME, "h": FRAME}, "rotated": False, "trimmed": False,
                "spriteSourceSize": {"x": 0, "y": 0, "w": FRAME, "h": FRAME}, "sourceSize": {"w": FRAME, "h": FRAME},
                "pivot": {"x": 0.5, "y": 0.5},
            }
    atlas.save(IMAGES / "symbols.png")
    meta = {"app": "scripts/trail_sprites.py", "image": "symbols.png", "format": "RGBA8888", "size": {"w": atlas.width, "h": atlas.height}, "scale": 1}
    (IMAGES / "symbols.json").write_text(json.dumps({"frames": frames, "meta": meta}, indent=1) + "\n", encoding="utf-8", newline="\n")

    for system, doc in targets.items():
        for v in doc["airborneSymbology"]:
            c = (v.get("historyTrailShape") or {}).get("color") or v.get("plotColor")
            if not isinstance(c, list):
                continue
            key = "%02x%02x%02x" % tuple(c[:3])
            v.pop("historyTrailShape", None)  # a trail shape would win over the images
            v["historyTrailImages"] = [f"trails/{key}/t{i + 1}" for i in range(len(DIAMETERS))]
        path = SYSTEMS / system / "targets.json"
        text = json.dumps(doc, indent=2, ensure_ascii=False)
        path.write_text(text + "\n", encoding="utf-8", newline="\n")
    print(f"{len(colors)} trail colours, {len(frames)} frames")


if __name__ == "__main__":
    main()
