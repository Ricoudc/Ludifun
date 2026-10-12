# Bibliothèque de figures (étape 22)

Cartes et schémas des activités « carte » (`MAP`) et « coloriage » (`COLORING`). Chaque figure
est un fichier JSON de `backend/app/figures/`, servi à l'application par `GET /v1/figures/{id}`.
Les zones portent un nom et des synonymes : une notion de la leçon dont le nom est celui d'une
zone (« la Bretagne », « le fémur », « Jupiter ») peut être travaillée sur la figure.

| Figure | Zones | Source | Licence |
| --- | --- | --- | --- |
| `france-regions` | 13 régions | IGN Admin Express via [france-geojson](https://github.com/gregoiredavid/france-geojson) | Licence Ouverte (Etalab) : citer la source |
| `france-departements` | 96 départements | idem | idem |
| `france-relief` | fleuves, montagnes, mers, 11 grandes villes | [Natural Earth](https://www.naturalearthdata.com/) ; Massif central et villes placés à la main | domaine public |
| `europe` | pays d'Europe (micro-États avec un repère) | Natural Earth | domaine public |
| `monde` | continents, océans, Méditerranée | Natural Earth | domaine public |
| `systeme-solaire`, `squelette`, `appareil-digestif`, `plante`, `cycle-de-l-eau`, `volcan`, `periodes-histoire` | parties du schéma | dessins faits pour Ludifun (`build_figures.py`) | à Ludifun |

La source de chaque figure (`credits`) est affichée sous le dessin dans l'application.

## Refaire les figures

```bash
python tools/figures/download.py                                   # données sources (non versionnées)
uv run --no-project --with shapely python tools/figures/build_figures.py
python tools/figures/preview.py                                    # aperçus SVG dans tools/figures/preview/
```

Changer le dessin d'une figure existante : augmenter `VERSION` dans `build_figures.py` (les
téléphones gardent une figure en mémoire le temps d'un lancement).

## Format

- `width` × `height` : unités de dessin, y vers le bas.
- `decor` : formes sans rôle (mer, pays voisins, sol), dessinées d'abord.
- `zones` : `id`, `name`, `aliases`, `kind` (`area` surface, `line` fleuve, `point` ville),
  `shapes` (polygones ; un polygone est une liste d'anneaux `[x0, y0, x1, y1…]`, le premier
  extérieur, les suivants des trous), `fill` facultatif, `marker` `[x, y, rayon]` pour une zone
  trop petite pour être touchée.
- `labels` : textes fixes (les dates de la frise).

Deux zones d'une même figure ne peuvent pas porter le même nom (vérifié par les tests).

## Ajouter une figure

1. Écrire sa fonction dans `build_figures.py` (formes shapely : `ellipse`, `tube`, `curve`…).
2. L'ajouter à `main()` et à `ORDER` dans `backend/app/domain/figures.py` (l'ordre départage
   deux figures qui conviennent : « Loire » fleuve plutôt que département).
3. Pour des images d'autres sources, ne prendre que du domaine public (CC0), de la Licence
   Ouverte ou du CC BY (et remplir `credits`) ; pas de CC BY-NC ni de CC BY-SA.
