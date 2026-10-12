"""Construit la bibliothèque de figures (étape 22) : cartes et schémas à zones nommées.

Les fichiers produits (`backend/app/figures/*.json`) sont versionnés dans le dépôt ; ce
programme ne sert qu'à les refaire. Il a besoin de shapely et des données sources :

    python tools/figures/download.py            # une fois (Natural Earth, contours IGN)
    uv run --with shapely python tools/figures/build_figures.py

Format d'une figure : `width` × `height` (unités de dessin, y vers le bas), `decor` (formes
sans rôle, dessinées d'abord), `zones` (ce que l'enfant touche ou colorie ; `kind` area, line
ou point ; `shapes` : polygones, chacun une liste d'anneaux [x0, y0, x1, y1…], le premier
extérieur, les suivants des trous), `labels` (textes fixes). Voir tools/figures/README.md.
"""

import json
import math
import re
import unicodedata
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[2]
SOURCES = Path(__file__).resolve().parent / "sources"
OUT = ROOT / "backend" / "app" / "figures"
VERSION = 1

NATURAL_EARTH = "Natural Earth (domaine public)"
IGN = "Contours : IGN Admin Express, Licence Ouverte (Etalab), via france-geojson"
LUDIFUN = "Dessin Ludifun"

SEA = "#d6e6f5"
LAND = "#f6f1e3"
NEIGHBOUR = "#e4e1d8"
MOUNTAIN = "#c9a37a"
RIVER = "#3d7cc9"
TINY_PX2 = 60.0  # en dessous, un repère rond aide à toucher la zone
TINY_RADIUS = 6.0

Project = Callable[[float, float], tuple[float, float]]


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def ring(coords: Iterable[tuple[float, float]]) -> list[float]:
    points = list(coords)
    if len(points) > 1 and points[0] == points[-1]:
        points = points[:-1]
    return [round(v, 1) for x, y in points for v in (x, y)]


def polygons(geom: BaseGeometry) -> list[list[list[float]]]:
    """Polygones (anneaux aplatis) d'une géométrie surfacique."""
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        rings = [ring(geom.exterior.coords), *(ring(i.coords) for i in geom.interiors)]
        return [[r for r in rings if len(r) >= 6]]
    if hasattr(geom, "geoms"):
        return [p for g in geom.geoms for p in polygons(g)]
    return []


def lines(geom: BaseGeometry) -> list[list[list[float]]]:
    if geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [[[round(v, 1) for x, y in geom.coords for v in (x, y)]]]
    if hasattr(geom, "geoms"):
        return [p for g in geom.geoms for p in lines(g)]
    return []


def zone(
    name: str,
    geom: BaseGeometry,
    *,
    kind: str = "area",
    aliases: Iterable[str] = (),
    fill: str | None = None,
    zone_id: str | None = None,
) -> dict[str, Any]:
    shapes = lines(geom) if kind == "line" else polygons(geom)
    result: dict[str, Any] = {
        "id": zone_id or slug(name),
        "name": name,
        "aliases": sorted(set(aliases)),
        "kind": kind,
        "shapes": shapes,
    }
    if fill:
        result["fill"] = fill
    if kind == "area" and geom.area < TINY_PX2:  # micro-État, petite île : un repère rond
        result["marker"] = [round(geom.centroid.x, 1), round(geom.centroid.y, 1), TINY_RADIUS]
    return result


def decor(
    geom: BaseGeometry, *, fill: str | None = None, stroke: str | None = None, width: float = 1
) -> dict[str, Any]:
    kind = "line" if isinstance(geom, LineString) or geom.geom_type == "MultiLineString" else "area"
    return {
        "kind": kind,
        "shapes": lines(geom) if kind == "line" else polygons(geom),
        "fill": fill,
        "stroke": stroke,
        "width": width,
    }


def label(text: str, x: float, y: float, size: float = 14) -> dict[str, Any]:
    return {"text": text, "x": x, "y": y, "size": size}


def write(
    figure_id: str,
    title: str,
    subject: str,
    credits: str,
    width: float,
    height: float,
    *,
    zones: list[dict[str, Any]],
    decors: list[dict[str, Any]] = (),
    labels: list[dict[str, Any]] = (),
) -> None:  # type: ignore[assignment]
    ids = [z["id"] for z in zones]
    assert len(ids) == len(set(ids)), f"{figure_id} : zones en double"
    assert all(z["shapes"] for z in zones), f"{figure_id} : zone vide"
    figure = {
        "id": figure_id,
        "version": VERSION,
        "title": title,
        "subject": subject,
        "credits": credits,
        "width": round(width),
        "height": round(height),
        "decor": list(decors),
        "zones": zones,
        "labels": list(labels),
    }
    path = OUT / f"{figure_id}.json"
    path.write_text(json.dumps(figure, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{figure_id:22} {len(zones):3} zones  {path.stat().st_size // 1024:4} Ko")


# --------------------------------------------------------------------------- #
# Cartes
# --------------------------------------------------------------------------- #


def load(name: str) -> list[dict[str, Any]]:
    return json.loads((SOURCES / f"{name}.geojson").read_text(encoding="utf-8"))["features"]


def projection(west: float, east: float, south: float, north: float, width: float) -> tuple[Project, float]:
    """Projection équirectangulaire corrigée à la latitude moyenne ; renvoie aussi la hauteur."""
    k = math.cos(math.radians((south + north) / 2))
    scale = width / ((east - west) * k)

    def project(lon: float, lat: float) -> tuple[float, float]:
        return (lon - west) * k * scale, (north - lat) * scale

    return project, (north - south) * scale


def to_plane(geom: BaseGeometry, project: Project, tolerance: float) -> BaseGeometry:
    planar = transform(lambda x, y, z=None: project(x, y), geom)
    return planar.simplify(tolerance, preserve_topology=True) if tolerance else planar


def clean(geom: BaseGeometry) -> BaseGeometry:
    geom = geom.buffer(0)
    if isinstance(geom, MultiPolygon):  # îlots invisibles à cette échelle
        kept = [p for p in geom.geoms if p.area > 0.5]
        geom = MultiPolygon(kept) if kept else geom
    return geom


FRANCE_BOX = (-5.6, 10.0, 41.2, 51.4)


def france_divisions(features: str, figure_id: str, title: str, aliases: dict[str, list[str]]) -> None:
    project, height = projection(*FRANCE_BOX, width=900)
    zones = []
    for f in load(features):
        name = f["properties"]["nom"]
        geom = clean(to_plane(shape(f["geometry"]), project, 0.6))
        zones.append(zone(name, geom, aliases=aliases.get(name, []), zone_id=slug(name)))
    zones.sort(key=lambda z: z["id"])
    sea = decor(box(0, 0, 900, height), fill=SEA)
    write(figure_id, title, "geography", IGN, 900, height, zones=zones, decors=[sea])


REGION_ALIASES = {
    "Centre-Val de Loire": ["Centre", "région Centre"],
    "Provence-Alpes-Côte d'Azur": ["PACA", "Provence"],
    "Auvergne-Rhône-Alpes": ["Auvergne Rhône-Alpes"],
    "Grand Est": ["région Grand Est"],
    "Île-de-France": ["région parisienne", "Ile de France"],
    "Hauts-de-France": ["région Hauts-de-France"],
    "Corse": ["île de Beauté"],
}

CITIES = {
    "Paris": (2.35, 48.86), "Lyon": (4.84, 45.76), "Marseille": (5.37, 43.30),
    "Toulouse": (1.44, 43.60), "Bordeaux": (-0.58, 44.84), "Lille": (3.06, 50.63),
    "Nantes": (-1.55, 47.22), "Strasbourg": (7.75, 48.58), "Nice": (7.27, 43.70),
    "Rennes": (-1.68, 48.11), "Montpellier": (3.88, 43.61),
}  # fmt: skip

MASSIF_CENTRAL = [
    (2.0, 46.3), (3.3, 46.2), (4.3, 45.9), (4.6, 45.2), (4.3, 44.4),
    (3.6, 43.8), (2.6, 43.6), (2.0, 44.2), (1.6, 45.0), (1.5, 45.8),
]  # fmt: skip

FRANCE_SEAS = {
    "Manche": ([(-6.5, 48.4), (-5.72, 50.05), (-3.0, 50.9), (1.3, 51.15), (1.65, 50.95), (1.0, 48.5), (-4.0, 48.3)], ["la Manche"]),
    "mer du Nord": ([(1.3, 51.15), (1.65, 50.95), (2.5, 50.9), (5.0, 51.3), (10.0, 51.3), (10.0, 51.4), (1.4, 51.4)], []),
    "océan Atlantique": ([(-6.5, 41.2), (-6.5, 48.4), (-4.0, 48.3), (0.0, 46.0), (-1.5, 43.2), (-5.6, 43.0), (-5.6, 41.2)], ["Atlantique", "golfe de Gascogne"]),
    "mer Méditerranée": ([(0.5, 41.2), (10.0, 41.2), (10.0, 44.0), (7.5, 44.2), (3.0, 43.6)], ["Méditerranée"]),
}  # fmt: skip

RIVERS = {"Seine": [], "Loire": [], "Garonne": [], "Rhône": ["Rhone"], "Rhin": ["Rhine"], "Dordogne": []}
MOUNTAINS = {
    "ALPS": ("Alpes", []),
    "PYRENEES": ("Pyrénées", []),
    "Jura": ("Jura", []),
    "Vosges": ("Vosges", []),
}


def france_relief() -> None:
    west, east, south, north = FRANCE_BOX
    project, height = projection(west, east, south, north, width=900)
    frame = box(west, south, east, north)
    countries = load("ne_50m_admin_0_countries")
    france = unary_union(
        [shape(f["geometry"]) for f in countries if f["properties"]["ADM0_A3"] == "FRA"]
    ).intersection(frame)
    land = unary_union([shape(f["geometry"]) for f in countries]).intersection(frame)
    neighbours = land.difference(france)
    near_france = france.buffer(0.05)
    decors = [
        decor(box(0, 0, 900, height), fill=SEA),
        decor(to_plane(neighbours, project, 0.5), fill=NEIGHBOUR, stroke="#b9b4a8"),
        decor(to_plane(france, project, 0.5), fill=LAND, stroke="#7d7564", width=1.5),
    ]
    zones = []
    for name, (points, aliases) in FRANCE_SEAS.items():
        water = Polygon(points).intersection(frame).difference(land)
        zones.append(zone(name, clean(to_plane(water, project, 0.5)), aliases=aliases, fill=SEA))
    for f in load("ne_10m_geography_regions_polys"):
        key = f["properties"].get("NAME")
        if f["properties"].get("FEATURECLA") == "Range/mtn" and key in MOUNTAINS:
            name, aliases = MOUNTAINS[key]
            area = shape(f["geometry"]).intersection(near_france)
            zones.append(zone(name, clean(to_plane(area, project, 0.5)), aliases=aliases, fill=MOUNTAIN))
    central = Polygon(MASSIF_CENTRAL)
    zones.append(zone("Massif central", to_plane(central, project, 0.5), fill=MOUNTAIN))
    by_river: dict[str, list[BaseGeometry]] = {}
    for f in load("ne_10m_rivers_lake_centerlines"):
        name = f["properties"].get("name")
        for river, aliases in RIVERS.items():
            if name == river or name in aliases:
                by_river.setdefault(river, []).append(shape(f["geometry"]))
    for river, parts in by_river.items():
        course = unary_union(parts).intersection(near_france)
        zones.append(
            zone(river, to_plane(course, project, 0.4), kind="line", aliases=RIVERS[river], fill=RIVER)
        )
    for city, (lon, lat) in CITIES.items():
        x, y = project(lon, lat)
        zones.append(zone(city, Point(x, y).buffer(5, quad_segs=4), kind="point"))
    write(
        "france-relief",
        "Fleuves, montagnes, mers et villes de France",
        "geography",
        NATURAL_EARTH,
        900,
        height,
        zones=zones,
        decors=decors,
    )


def europe() -> None:
    west, east, south, north = -25.0, 45.0, 34.0, 71.5
    project, height = projection(west, east, south, north, width=900)
    frame = box(west, south, east, north)
    countries = load("ne_50m_admin_0_countries")
    kept_out = {"GGY", "JEY", "ALD", "IMN", "FRO"}
    aliases = {
        "Tchéquie": ["République tchèque"], "Pays-Bas": ["Hollande"], "Macédoine du Nord": ["Macédoine"],
        "Bosnie-Herzégovine": ["Bosnie"], "Biélorussie": ["Bélarus"], "Moldavie": ["Moldova"],
        "Cité du Vatican": ["Vatican"], "Royaume-Uni": ["Grande-Bretagne"],
    }  # fmt: skip
    zones, others = [], []
    for f in countries:
        props = f["properties"]
        geom = shape(f["geometry"]).intersection(frame)
        if geom.is_empty:
            continue
        if (props["CONTINENT"] == "Europe" or props["ADM0_A3"] == "CYP") and props["ADM0_A3"] not in kept_out:
            name = props["NAME_FR"]
            planar = clean(to_plane(geom, project, 0.4))
            zones.append(zone(name, planar, aliases=aliases.get(name, [])))
        else:
            others.append(geom)
    zones.sort(key=lambda z: z["id"])
    decors = [
        decor(box(0, 0, 900, height), fill=SEA),
        decor(to_plane(unary_union(others), project, 0.5), fill=NEIGHBOUR, stroke="#b9b4a8"),
    ]
    write("europe", "Les pays d'Europe", "geography", NATURAL_EARTH, 900, height, zones=zones, decors=decors)


WORLD_OCEANS = {
    "océan Atlantique": [(-100, 66), (30, 66), (12, 55), (-1, 43), (-5.6, 36.0), (-5, 30), (10, 10), (15, -10),
                         (20, -35), (20, -60), (-67, -60), (-69, -56), (-69, -18), (-78, 8), (-84, 11),
                         (-92, 17), (-95, 17.5), (-100, 20)],
    "océan Indien": [(20, 30), (100, 30), (104, 0), (115, -9), (130, -11), (135, -14), (147, -44), (147, -60),
                     (20, -60), (20, -35), (32, 30)],
    "océan Arctique": [(-180, 66), (180, 66), (180, 84), (-180, 84)],
    "océan Austral": [(-180, -60), (180, -60), (180, -80), (-180, -80)],
    "mer Méditerranée": [(-5.6, 30), (-5.6, 36.2), (0, 44), (15, 46.5), (26, 41), (28, 40.5), (30, 40), (37, 37), (37, 30)],
}  # fmt: skip
PACIFIC = [
    [(-180, 66), (-100, 66), (-100, 20), (-95, 17.5), (-92, 17), (-84, 11), (-78, 8), (-69, -18), (-69, -56),
     (-67, -60), (-180, -60)],
    [(100, 66), (180, 66), (180, -60), (147, -60), (147, -44), (135, -14), (130, -11), (115, -9), (104, 0), (100, 30)],
]  # fmt: skip
CONTINENTS = {
    "Africa": ("Afrique", []), "Asia": ("Asie", []), "Europe": ("Europe", []),
    "North America": ("Amérique du Nord", []), "South America": ("Amérique du Sud", []),
    "Oceania": ("Océanie", ["Australie"]), "Antarctica": ("Antarctique", ["Antarctide"]),
}  # fmt: skip


def world() -> None:
    west, east, south, north = -180.0, 180.0, -80.0, 84.0
    scale = 1000 / (east - west)
    height = (north - south) * scale

    def project(lon: float, lat: float) -> tuple[float, float]:
        return (lon - west) * scale, (north - lat) * scale

    frame = box(west, south, east, north)
    parts: dict[str, list[BaseGeometry]] = {}
    for f in load("ne_110m_admin_0_countries"):
        props = f["properties"]
        continent = props["CONTINENT"]
        if continent not in CONTINENTS:
            continue
        geom = shape(f["geometry"]).intersection(frame)
        if props["ADM0_A3"] == "RUS":  # l'Oural sépare l'Europe de l'Asie
            parts.setdefault("Europe", []).append(geom.intersection(box(-180, -90, 60, 90)))
            parts.setdefault("Asia", []).append(geom.difference(box(-180, -90, 60, 90)))
            continue
        if props["ADM0_A3"] == "FRA":  # la Guyane est en Amérique du Sud
            parts.setdefault("South America", []).append(geom.intersection(box(-180, -90, -20, 90)))
            geom = geom.difference(box(-180, -90, -20, 90))
        parts.setdefault(continent, []).append(geom)
    land = unary_union([shape(f["geometry"]) for f in load("ne_110m_land")]).intersection(frame)
    zones = []
    for key, (name, aliases) in CONTINENTS.items():
        geom = clean(to_plane(unary_union(parts[key]), project, 0.3))
        zones.append(zone(name, geom, aliases=aliases, fill=LAND))
    med = Polygon(WORLD_OCEANS["mer Méditerranée"])
    for name, points in WORLD_OCEANS.items():
        water = Polygon(points).intersection(frame).difference(land)
        if name != "mer Méditerranée":
            water = water.difference(med)
        zones.append(
            zone(name, clean(to_plane(water, project, 0.3)), aliases=[name.split(" ", 1)[1]], fill=SEA)
        )
    pacific = unary_union([Polygon(p) for p in PACIFIC]).intersection(frame).difference(land)
    zones.append(
        zone("océan Pacifique", clean(to_plane(pacific, project, 0.3)), aliases=["Pacifique"], fill=SEA)
    )
    write(
        "monde",
        "Continents et océans",
        "geography",
        NATURAL_EARTH,
        1000,
        height,
        zones=zones,
        decors=[decor(box(0, 0, 1000, height), fill=SEA)],
    )


# --------------------------------------------------------------------------- #
# Schémas dessinés
# --------------------------------------------------------------------------- #


def ellipse(cx: float, cy: float, rx: float, ry: float, angle: float = 0) -> Polygon:
    shape_ = affinity.scale(Point(cx, cy).buffer(1, quad_segs=16), rx, ry)
    return affinity.rotate(shape_, angle, origin=(cx, cy)) if angle else shape_


def tube(points: list[tuple[float, float]], width: float) -> Polygon:
    return LineString(points).buffer(width / 2, quad_segs=6)


def curve(
    p0: tuple[float, float], p1: tuple[float, float], p2: tuple[float, float], n: int = 16
) -> list[tuple[float, float]]:
    """Courbe de Bézier quadratique échantillonnée."""
    return [
        ((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t**2 * p2[0],
         (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t**2 * p2[1])
        for t in (i / n for i in range(n + 1))
    ]  # fmt: skip


def both(make: Callable[[int], BaseGeometry]) -> BaseGeometry:
    """Une forme et son symétrique (côté gauche et côté droit du corps)."""
    return unary_union([make(-1), make(1)])


def solar_system() -> None:
    w, h = 1000, 320
    cy = 160
    sun = Point(-170, cy).buffer(250, quad_segs=32).intersection(box(0, 0, w, h))
    planets = [
        ("Mercure", 120, 7, "#b0a89c"), ("Vénus", 165, 12, "#e8c77f"), ("Terre", 220, 13, "#4f8fd6"),
        ("Mars", 272, 9, "#d0643c"), ("Jupiter", 390, 46, "#d9b08c"), ("Saturne", 560, 38, "#e6cf8f"),
        ("Uranus", 720, 24, "#9fd8df"), ("Neptune", 850, 23, "#4a6fd1"),
    ]  # fmt: skip
    decors = [decor(box(0, 0, w, h), fill="#10163a")]
    for _, x, _, _ in planets:
        radius = x + 170
        arc = Point(-170, cy).buffer(radius, quad_segs=64).exterior.intersection(box(0, 10, w, h - 10))
        decors.append(decor(arc, stroke="#3a4270", width=1))
    zones = [zone("Soleil", sun, fill="#ffc83d")]
    for name, x, r, colour in planets:
        aliases = ["planète " + name]
        zones.append(zone(name, Point(x, cy).buffer(r, quad_segs=16), aliases=aliases, fill=colour))
    ring_ = ellipse(560, cy, 66, 13, -12).difference(ellipse(560, cy, 48, 8, -12))
    decors_top = decor(
        ring_.difference(Point(560, cy).buffer(38).intersection(box(0, 0, w, cy))), fill="#c8b27a"
    )
    zones.append(
        zone(
            "Lune",
            Point(220, cy - 26).buffer(4, quad_segs=8),
            kind="point",
            aliases=["satellite de la Terre"],
        )
    )
    write(
        "systeme-solaire",
        "Le système solaire",
        "science",
        LUDIFUN,
        w,
        h,
        zones=zones,
        decors=[*decors, decors_top],
    )


def skeleton() -> None:
    w, h, c = 600, 1010, 300
    zones = [
        zone("colonne vertébrale", tube([(c, 170), (c, 575)], 20), aliases=["vertèbres", "colonne"]),
        zone("crâne", ellipse(c, 92, 60, 72), aliases=["boîte crânienne"]),
        zone(
            "mâchoire",
            tube(curve((c - 44, 140), (c, 205), (c + 44, 140)), 14),
            aliases=["mandibule", "maxillaire inférieur"],
        ),
        zone(
            "côtes",
            both(
                lambda s: unary_union(
                    [
                        tube(
                            curve(
                                (c + s * 10, 232 + i * 30),
                                (c + s * 135, 222 + i * 30),
                                (c + s * 26, 262 + i * 30 + i * 2),
                            ),
                            9,
                        )
                        for i in range(7)
                    ]
                )
            ),
            aliases=["cage thoracique", "côte"],
        ),
        zone("sternum", tube([(c, 228), (c, 392)], 20)),
        zone(
            "clavicule",
            both(lambda s: tube([(c + s * 14, 208), (c + s * 104, 196)], 12)),
            aliases=["clavicules"],
        ),
        zone(
            "humérus",
            both(
                lambda s: unary_union(
                    [tube([(c + s * 112, 205), (c + s * 136, 392)], 18), Point(c + s * 110, 205).buffer(15)]
                )
            ),
            aliases=["humerus"],
        ),
        zone("radius", both(lambda s: tube([(c + s * 146, 402), (c + s * 162, 560)], 10))),
        zone("cubitus", both(lambda s: tube([(c + s * 128, 402), (c + s * 142, 562)], 10)), aliases=["ulna"]),
        zone(
            "os de la main",
            both(
                lambda s: unary_union(
                    [
                        ellipse(c + s * 154, 588, 20, 22),
                        *(
                            tube(
                                [
                                    (c + s * (138 + 8 * i), 600),
                                    (c + s * (132 + 11 * i), 650 - abs(i - 2) * 6),
                                ],
                                7,
                            )
                            for i in range(5)
                        ),
                    ]
                )
            ),
            aliases=["main", "phalanges", "carpe", "métacarpe", "os des doigts"],
        ),
        zone(
            "bassin",
            unary_union([ellipse(c - 45, 590, 58, 40, 15), ellipse(c + 45, 590, 58, 40, -15)]).difference(
                unary_union([ellipse(c - 40, 612, 15, 11), ellipse(c + 40, 612, 15, 11)])
            ),
            aliases=["os du bassin", "hanche", "os iliaque"],
        ),
        zone(
            "fémur",
            both(
                lambda s: unary_union(
                    [tube([(c + s * 70, 622), (c + s * 74, 800)], 22), Point(c + s * 62, 618).buffer(16)]
                )
            ),
            aliases=["femur"],
        ),
        zone("tibia", both(lambda s: tube([(c + s * 70, 832), (c + s * 64, 962)], 18))),
        zone(
            "péroné",
            both(lambda s: tube([(c + s * 94, 840), (c + s * 86, 958)], 8)),
            aliases=["fibula", "perone"],
        ),
        zone("rotule", both(lambda s: Point(c + s * 74, 816).buffer(13)), aliases=["patella"]),
        zone(
            "os du pied",
            both(lambda s: ellipse(c + s * 74, 985, 34, 14)),
            aliases=["pied", "orteils", "tarse", "métatarse"],
        ),
    ]
    write("squelette", "Le squelette humain", "science", LUDIFUN, w, h, zones=zones)


def digestion() -> None:
    w, h, c = 600, 860, 300
    body = unary_union(
        [
            Point(c, 90).buffer(70),
            tube([(c, 150), (c, 200)], 70),
            Polygon([(150, 230), (450, 230), (470, 780), (130, 780)]).buffer(30),
        ]
    )
    zones = [
        zone("bouche", ellipse(c, 122, 24, 9), aliases=["cavité buccale"]),
        zone("œsophage", tube([(c, 132), (c, 250), (322, 330)], 16), aliases=["oesophage", "oesophage"]),
        zone(
            "foie",
            Polygon([(185, 330), (330, 312), (348, 345), (292, 398), (205, 412), (172, 376)]).buffer(6),
        ),
        zone("vésicule biliaire", ellipse(262, 410, 13, 9), aliases=["vesicule"]),
        zone("pancréas", tube([(262, 468), (330, 460), (392, 446)], 20), aliases=["pancreas"]),
        zone("estomac", tube([(322, 332), (372, 350), (388, 395), (352, 432), (306, 428)], 50)),
        zone(
            "gros intestin",
            tube([(212, 700), (208, 505), (392, 500), (398, 690), (330, 728), (c, 762)], 42),
            aliases=["côlon", "colon", "rectum"],
        ),
        zone(
            "intestin grêle",
            unary_union(
                [tube([(258, y), (346, y)], 26) for y in range(552, 700, 24)]
                + [
                    tube(
                        [
                            (346 if i % 2 == 0 else 258, 552 + i * 24),
                            (346 if i % 2 == 0 else 258, 576 + i * 24),
                        ],
                        26,
                    )
                    for i in range(6)
                ]
            ),
            aliases=["intestin grele", "petit intestin"],
        ),
        zone("appendice", tube([(196, 722), (190, 752)], 9)),
        zone("anus", Point(c, 792).buffer(8), kind="point"),
    ]
    write(
        "appareil-digestif",
        "L'appareil digestif",
        "science",
        LUDIFUN,
        w,
        h,
        zones=zones,
        decors=[decor(body, fill="#fde3cf", stroke="#e0b596", width=2)],
    )


def plant() -> None:
    w, h, c = 600, 800, 300
    soil = box(0, 560, w, h)
    petals = unary_union(
        [
            ellipse(c + 42 * math.cos(a), 165 + 42 * math.sin(a), 30, 16, math.degrees(a))
            for a in (i * math.pi / 3 for i in range(6))
        ]
    )
    stamens = unary_union(
        [
            Point(c + 22 * math.cos(a), 165 + 22 * math.sin(a)).buffer(5)
            for a in (i * math.pi / 4 for i in range(8))
        ]
    )
    zones = [
        zone(
            "racines",
            unary_union(
                [
                    tube([(c, 560), (c, 760)], 10),
                    tube([(c, 600), (238, 680)], 7),
                    tube([(c, 622), (366, 702)], 7),
                    tube([(c, 680), (256, 752)], 5),
                    tube([(c, 700), (348, 772)], 5),
                ]
            ),
            aliases=["racine"],
        ),
        zone("tige", tube([(c, 560), (c, 205)], 18), aliases=["tronc"]),
        zone(
            "feuilles",
            unary_union(
                [
                    ellipse(236, 432, 60, 20, -25),
                    ellipse(364, 362, 60, 20, 25),
                    ellipse(246, 292, 46, 16, -30),
                    tube([(c, 450), (270, 438)], 5),
                    tube([(c, 380), (330, 368)], 5),
                ]
            ),
            aliases=["feuille"],
        ),
        zone("bourgeon", ellipse(314, 492, 9, 15, 25)),
        zone(
            "sépales",
            unary_union([ellipse(282, 205, 20, 8, 35), ellipse(318, 205, 20, 8, -35)]),
            aliases=["sepales", "sépale"],
        ),
        zone("pétales", petals.difference(Point(c, 165).buffer(26)), aliases=["pétale", "corolle", "fleur"]),
        zone("étamines", stamens, aliases=["étamine", "etamines"]),
        zone("pistil", Point(c, 165).buffer(12), aliases=["ovaire", "cœur de la fleur"]),
    ]
    write(
        "plante",
        "Les parties d'une plante",
        "science",
        LUDIFUN,
        w,
        h,
        zones=zones,
        decors=[decor(soil, fill="#c9a782"), decor(box(0, 0, w, 560), fill="#eaf5ff")],
    )


def arrow(points: list[tuple[float, float]], width: float) -> BaseGeometry:
    (x1, y1), (x2, y2) = points[-2], points[-1]
    angle = math.atan2(y2 - y1, x2 - x1)
    head = Polygon([
        (x2 + 16 * math.cos(angle), y2 + 16 * math.sin(angle)),
        (x2 + 12 * math.cos(angle + 2.3), y2 + 12 * math.sin(angle + 2.3)),
        (x2 + 12 * math.cos(angle - 2.3), y2 + 12 * math.sin(angle - 2.3)),
    ])  # fmt: skip
    return unary_union([tube(points, width), head])


def water_cycle() -> None:
    w, h = 1000, 620
    ground = Polygon([(420, 470), (1000, 470), (1000, 620), (470, 620)])
    zones = [
        zone("soleil", Point(900, 90).buffer(52), fill="#ffc83d"),
        zone(
            "mer",
            Polygon([(0, 470), (420, 470), (470, 620), (0, 620)]),
            aliases=["océan", "océans"],
            fill="#5b9bd5",
        ),
        zone(
            "montagne",
            Polygon([(560, 472), (720, 228), (880, 472)]),
            fill="#9c8a74",
            aliases=["montagnes", "relief"],
        ),
        zone(
            "neige",
            Polygon([(688, 276), (720, 228), (752, 276), (736, 288), (720, 272), (704, 288)]),
            aliases=["glacier", "glaciers", "fonte des neiges"],
            fill="#ffffff",
        ),
        zone(
            "évaporation",
            unary_union(
                [arrow([(x, 440), (x + 14, 380), (x - 6, 320), (x + 8, 270)], 7) for x in (100, 190, 280)]
            ),
            aliases=["vapeur d'eau", "vapeur", "evaporation"],
            fill="#e07a5f",
        ),
        zone(
            "nuages",
            unary_union(
                [
                    Point(x, y).buffer(r)
                    for x, y, r in (
                        (190, 170, 45),
                        (240, 150, 55),
                        (295, 175, 40),
                        (520, 130, 50),
                        (580, 110, 60),
                        (640, 135, 45),
                    )
                ]
            ),
            aliases=["nuage", "condensation"],
            fill="#eef1f5",
        ),
        zone(
            "pluie",
            unary_union(
                [tube([(x, y), (x - 10, y + 32)], 4) for x in range(520, 660, 22) for y in (205, 255)]
            ),
            aliases=["précipitations", "precipitations", "averse"],
            fill="#3d7cc9",
        ),
        zone(
            "rivière",
            tube([(700, 430), (640, 452), (560, 470), (480, 482), (420, 478)], 14),
            aliases=["ruissellement", "fleuve", "cours d'eau", "riviere"],
            fill="#3d7cc9",
        ),
        zone(
            "infiltration",
            unary_union([arrow([(x, 488), (x - 4, 548)], 6) for x in (760, 830, 900)]),
            aliases=["infiltration de l'eau"],
            fill="#e07a5f",
        ),
        zone(
            "nappe phréatique",
            ellipse(820, 596, 170, 14),
            aliases=["nappe", "eaux souterraines", "eau souterraine"],
            fill="#7fb2e5",
        ),
    ]
    write(
        "cycle-de-l-eau",
        "Le cycle de l'eau",
        "science",
        LUDIFUN,
        w,
        h,
        zones=zones,
        decors=[decor(box(0, 0, w, 470), fill="#eaf5ff"), decor(ground, fill="#b8d98f")],
    )


def volcano() -> None:
    w, h, c = 700, 700, 350
    zones = [
        zone(
            "cône volcanique",
            Polygon([(70, 560), (300, 236), (400, 236), (630, 560)]),
            aliases=["cône", "cone", "volcan"],
            fill="#8a6f5a",
        ),
        zone(
            "chambre magmatique",
            ellipse(c, 638, 130, 40),
            aliases=["réservoir magmatique", "poche de magma", "magma"],
            fill="#e8552d",
        ),
        zone(
            "cheminée",
            tube([(c, 610), (c, 236)], 26),
            aliases=["cheminée volcanique", "cheminee"],
            fill="#e8552d",
        ),
        zone("cratère", ellipse(c, 232, 52, 12), aliases=["cratere"], fill="#5b4636"),
        zone(
            "coulée de lave",
            tube([(392, 244), (432, 302), (470, 362), (502, 432), (560, 540)], 30),
            aliases=["lave", "coulee de lave", "coulées de lave"],
            fill="#f28a2e",
        ),
        zone(
            "panache de cendres",
            unary_union(
                [
                    Point(x, y).buffer(r)
                    for x, y, r in ((c, 170, 40), (320, 120, 48), (385, 105, 52), (340, 60, 44))
                ]
            ),
            aliases=["nuage de cendres", "cendres", "panache volcanique", "fumée"],
            fill="#9aa0a6",
        ),
        zone(
            "bombes volcaniques",
            unary_union([Point(x, y).buffer(9) for x, y in ((210, 130), (500, 90), (160, 210), (540, 190))]),
            aliases=["bombes", "projections"],
            fill="#5b4636",
        ),
    ]
    write(
        "volcan",
        "Le volcan",
        "science",
        LUDIFUN,
        w,
        h,
        zones=zones,
        decors=[decor(box(0, 0, w, 560), fill="#eaf5ff"), decor(box(0, 560, w, h), fill="#c9a782")],
    )


def history_periods() -> None:
    w, h = 1000, 200
    periods = [
        ("Préhistoire", 0, 220, "#c9b79c", []), ("Antiquité", 220, 420, "#e6c98f", []),
        ("Moyen Âge", 420, 620, "#a9c7a0", ["Moyen Age", "Moyen-Âge"]),
        ("Temps modernes", 620, 780, "#9fc2dc", ["Époque moderne", "Epoque moderne"]),
        ("Époque contemporaine", 780, 990, "#d7a8c9", ["période contemporaine", "Epoque contemporaine"]),
    ]  # fmt: skip
    zones = [
        zone(name, box(x0 + 2, 60, x1 - 2, 130), aliases=aliases, fill=colour)
        for name, x0, x1, colour, aliases in periods
    ]
    ticks = [(220, "vers −3000"), (420, "476"), (620, "1492"), (780, "1789")]
    decors = [decor(LineString([(0, 150), (990, 150)]), stroke="#555555", width=3)]
    decors += [decor(LineString([(x, 140), (x, 160)]), stroke="#555555", width=3) for x, _ in ticks]
    labels = [label(text, x, 178, 16) for x, text in ticks] + [label("aujourd'hui", 950, 178, 14)]
    write(
        "periodes-histoire",
        "Les grandes périodes de l'histoire",
        "history",
        LUDIFUN,
        w,
        h,
        zones=zones,
        decors=decors,
        labels=labels,
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    france_divisions("regions", "france-regions", "Les régions de France", REGION_ALIASES)
    france_divisions("departements", "france-departements", "Les départements de France", {})
    france_relief()
    europe()
    world()
    solar_system()
    skeleton()
    digestion()
    plant()
    water_cycle()
    volcano()
    history_periods()


if __name__ == "__main__":
    main()
