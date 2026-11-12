"""Figures des cartes et du coloriage (étape 22) : données publiques, les mêmes pour tous."""

from functools import cache

from fastapi import APIRouter, Response

from app.api.errors import ApiError
from app.domain.figures import figure_path

router = APIRouter(tags=["activités"])
CACHE = "public, max-age=604800"  # la version de la figure est dans la charge utile de l'activité


@cache
def _content(figure_id: str) -> bytes | None:
    path = figure_path(figure_id)
    return path.read_bytes() if path is not None else None


@router.get("/figures/{figure_id}", response_class=Response)
async def get_figure(figure_id: str) -> Response:
    """Une figure : zones nommées (à toucher, à colorier), décor et textes fixes."""
    content = _content(figure_id)
    if content is None:
        raise ApiError(404, "figure_not_found", "Figure introuvable.")
    return Response(content, media_type="application/json", headers={"Cache-Control": CACHE})
