"""Télécharge les données sources des cartes dans tools/figures/sources/ (non versionné)."""

import urllib.request
from pathlib import Path

SOURCES = Path(__file__).resolve().parent / "sources"
NATURAL_EARTH = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
FRANCE_GEOJSON = "https://raw.githubusercontent.com/gregoiredavid/france-geojson/master/"
FILES = {
    "ne_110m_admin_0_countries.geojson": NATURAL_EARTH + "ne_110m_admin_0_countries.geojson",
    "ne_110m_land.geojson": NATURAL_EARTH + "ne_110m_land.geojson",
    "ne_50m_admin_0_countries.geojson": NATURAL_EARTH + "ne_50m_admin_0_countries.geojson",
    "ne_10m_rivers_lake_centerlines.geojson": NATURAL_EARTH + "ne_10m_rivers_lake_centerlines.geojson",
    "ne_10m_geography_regions_polys.geojson": NATURAL_EARTH + "ne_10m_geography_regions_polys.geojson",
    "regions.geojson": FRANCE_GEOJSON + "regions-version-simplifiee.geojson",
    "departements.geojson": FRANCE_GEOJSON + "departements-version-simplifiee.geojson",
}

if __name__ == "__main__":
    SOURCES.mkdir(exist_ok=True)
    for name, url in FILES.items():
        print(name)
        urllib.request.urlretrieve(url, SOURCES / name)
