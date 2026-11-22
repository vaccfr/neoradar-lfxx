"""B612 Mono Bold with a barred zero, so 0 and O differ on the scope (B612 draws them alike).

    python scripts/font_zero.py <B612Mono-Bold.ttf from github.com/polarsys/b612>

Writes shared/package/fonts/B612MonoLFXX-Bold.ttf, family "B612 Mono LFXX". B612 is SIL OFL with
no reserved font name, so a modified copy may ship; keep B612-OFL.txt beside it.
"""
import sys
from pathlib import Path

from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

OUT = Path(__file__).resolve().parent.parent / "shared" / "package" / "fonts" / "B612MonoLFXX-Bold.ttf"
FAMILY, STYLE = "B612 Mono LFXX", "Bold"


def ellipse(pen, cx, cy, rx, ry):
    """Clockwise (filled in TrueType) ellipse from four quadratic arcs."""
    k = 0.4142  # tan(22.5°): two off-curve points per quarter
    pen.moveTo((cx, cy + ry))
    pen.qCurveTo((cx + rx * k, cy + ry), (cx + rx, cy + ry * k), (cx + rx, cy))
    pen.qCurveTo((cx + rx, cy - ry * k), (cx + rx * k, cy - ry), (cx, cy - ry))
    pen.qCurveTo((cx - rx * k, cy - ry), (cx - rx, cy - ry * k), (cx - rx, cy))
    pen.qCurveTo((cx - rx, cy + ry * k), (cx - rx * k, cy + ry), (cx, cy + ry))
    pen.closePath()


def main(src):
    font = TTFont(src)
    glyf = font["glyf"]
    zero = glyf["zero"]
    rec = RecordingPen()
    zero.draw(rec, glyf)
    # The counter is the inner contour; a bar in its middle, half its width and 60% of its height (a dot vanishes at 12 px).
    coords, ends, _ = zero.getCoordinates(glyf)
    inner = coords[ends[0] + 1:ends[1] + 1]
    xs, ys = [p[0] for p in inner], [p[1] for p in inner]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    pen = TTGlyphPen(glyf)
    rec.replay(pen)
    ellipse(pen, round(cx), round(cy), round((max(xs) - min(xs)) * 0.26), round((max(ys) - min(ys)) * 0.29))
    glyf["zero"] = pen.glyph()
    glyf["zero"].recalcBounds(glyf)

    for table in ("DSIG",):  # the signature no longer matches
        if table in font:
            del font[table]
    for rec_ in font["name"].names:
        value = {1: FAMILY, 4: f"{FAMILY} {STYLE}", 6: f"{FAMILY.replace(' ', '')}-{STYLE}",
                 16: FAMILY, 3: f"{FAMILY.replace(' ', '')}-{STYLE}"}.get(rec_.nameID)
        if value:
            rec_.string = value
    font.save(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    main(sys.argv[1])
