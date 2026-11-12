"""Rendu en PNG des figures exactes et des schémas dessinés par le code (§5.61).

Le domaine (`app.domain.diagrams`) donne des points et des textes ; ici on les peint avec
Pillow, sur fond blanc, dessinés deux fois plus grands puis réduits (traits nets). Aucune carte
graphique, aucune IA : quelques millisecondes.
"""

import io
import itertools
import logging
import math
from functools import cache

from PIL import Image, ImageDraw, ImageFont

from app.domain.diagrams import Disc, Drawing, Label, Point, Stroke

OUTPUT_WIDTH = 1024
SUPERSAMPLE = 2
DASH, GAP = 16.0, 11.0

Font = ImageFont.FreeTypeFont | ImageFont.ImageFont
logger = logging.getLogger("ludifun.images")


@cache
def _font(size: int, bold: bool) -> Font:
    """DejaVu Sans (installé dans l'image Docker : accents, « ² »), sinon la police fournie avec
    Pillow, qui n'a pas les accents."""
    names = ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf") if bold else ("DejaVuSans.ttf",)
    for name in names:
        for folder in ("", "/usr/share/fonts/truetype/dejavu/"):
            try:
                return ImageFont.truetype(folder + name, size)
            except OSError:
                continue
    logger.warning("Police DejaVu absente : les accents des figures ne s'afficheront pas")
    return ImageFont.load_default(size=size)


def _dashed(draw: ImageDraw.ImageDraw, points: list[Point], color: str, width: int) -> None:
    for (x1, y1), (x2, y2) in itertools.pairwise(points):
        length = math.hypot(x2 - x1, y2 - y1)
        if length == 0:
            continue
        dx, dy = (x2 - x1) / length, (y2 - y1) / length
        t = 0.0
        while t < length:
            end = min(t + DASH * SUPERSAMPLE, length)
            draw.line([(x1 + dx * t, y1 + dy * t), (x1 + dx * end, y1 + dy * end)], fill=color, width=width)
            t = end + GAP * SUPERSAMPLE


def render(drawing: Drawing, width: int = OUTPUT_WIDTH) -> bytes:
    """Le PNG du dessin, `width` pixels de large (hauteur proportionnelle)."""
    k = width * SUPERSAMPLE / drawing.width
    size = (round(drawing.width * k), round(drawing.height * k))
    image = Image.new("RGB", size, "#ffffff")
    draw = ImageDraw.Draw(image)

    def scale(p: Point) -> Point:
        return (p[0] * k, p[1] * k)

    for item in drawing.items:
        if isinstance(item, Stroke):
            points = [scale(p) for p in item.points]
            line_width = max(round(item.width * k), 1)
            if item.closed and item.fill:
                draw.polygon(points, fill=item.fill)
            path = [*points, points[0]] if item.closed else points
            if item.width <= 0 or len(path) < 2:
                continue
            if item.dashed:
                _dashed(draw, path, item.color, line_width)
            else:
                draw.line(path, fill=item.color, width=line_width, joint="curve")
        elif isinstance(item, Disc):
            cx, cy = scale(item.center)
            r = item.radius * k
            box = [cx - r, cy - r, cx + r, cy + r]
            if item.fill:
                draw.ellipse(box, fill=item.fill)
            if item.width > 0:
                draw.ellipse(box, outline=item.color, width=max(round(item.width * k), 1))
        elif isinstance(item, Label):
            draw.text(
                scale(item.at),
                item.text,
                fill=item.color,
                font=_font(round(item.size * k), item.bold),
                anchor="mm",
            )
    image = image.resize((width, round(size[1] * width / size[0])), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()
