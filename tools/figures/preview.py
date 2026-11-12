"""Aperçu des figures en SVG (tools/figures/preview/), pour les vérifier à l'œil."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIGURES = ROOT / "backend" / "app" / "figures"
OUT = Path(__file__).resolve().parent / "preview"
PALETTE = ["#f28e8e", "#8ec5f2", "#a8e0a0", "#f5d37a", "#c9a8f0", "#f5b77a", "#8fe0d6", "#e8a0c8"]


def path(polygon: list[list[float]], closed: bool) -> str:
    parts = []
    for ring in polygon:
        points = " L ".join(f"{ring[i]} {ring[i + 1]}" for i in range(0, len(ring), 2))
        parts.append(f"M {points}{' Z' if closed else ''}")
    return " ".join(parts)


def svg(figure: dict) -> str:
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {figure["width"]} {figure["height"]}" '
        f'width="{figure["width"]}" height="{figure["height"]}" font-family="sans-serif">'
    ]
    for d in figure["decor"]:
        closed = d["kind"] == "area"
        for polygon in d["shapes"]:
            out.append(
                f'<path d="{path(polygon, closed)}" fill="{d["fill"] or "none"}" fill-rule="evenodd" '
                f'stroke="{d["stroke"] or "none"}" stroke-width="{d["width"]}"/>'
            )
    for i, z in enumerate(figure["zones"]):
        colour = z.get("fill") or PALETTE[i % len(PALETTE)]
        for polygon in z["shapes"]:
            if z["kind"] == "line":
                out.append(
                    f'<path d="{path(polygon, False)}" fill="none" stroke="{colour}" stroke-width="3"/>'
                )
            else:
                out.append(
                    f'<path d="{path(polygon, True)}" fill="{colour}" fill-rule="evenodd" stroke="#333" stroke-width="0.7"/>'
                )
        if "marker" in z:
            x, y, r = z["marker"]
            out.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="none" stroke="#333"/>')
    for z in figure["zones"]:  # noms, pour vérifier
        ring = z["shapes"][0][0]
        xs, ys = ring[0::2], ring[1::2]
        out.append(
            f'<text x="{sum(xs) / len(xs):.0f}" y="{sum(ys) / len(ys):.0f}" font-size="10" fill="#c00">{z["name"]}</text>'
        )
    for label in figure["labels"]:
        out.append(
            f'<text x="{label["x"]}" y="{label["y"]}" font-size="{label["size"]}" text-anchor="middle">{label["text"]}</text>'
        )
    out.append("</svg>")
    return "\n".join(out)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for file in sorted(FIGURES.glob("*.json")):
        (OUT / f"{file.stem}.svg").write_text(
            svg(json.loads(file.read_text(encoding="utf-8"))), encoding="utf-8"
        )
        print(file.stem)
