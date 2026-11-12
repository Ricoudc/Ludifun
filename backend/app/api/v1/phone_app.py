"""Application du téléphone servie par le serveur de la maison (spécification technique §5.50).

Le script Windows de mise à jour range dans le dossier `telephone/` l'APK de test publié par
GitHub (`ludifun.apk`) et sa fiche (`ludifun.json` : `{"build": numéro, "commit": …}`). Le
téléphone demande la dernière version au démarrage ; s'il est plus ancien, il propose de
télécharger l'APK ici, sans câble ni courriel. Routes anonymes : l'application n'est pas secrète.
"""

import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.deps import AppSettings
from app.api.errors import ApiError

router = APIRouter(prefix="/app", tags=["application"])

APK = "ludifun.apk"
CARD = "ludifun.json"
APK_TYPE = "application/vnd.android.package-archive"


class AppVersionOut(BaseModel):
    build: int | None  # numéro de la version ; None : fiche absente ou illisible
    size: int  # octets
    url: str  # à ajouter à l'adresse du serveur


def _apk(folder: Path | None) -> Path:
    path = folder / APK if folder is not None else None
    if path is None or not path.is_file():
        raise ApiError(404, "no_phone_app", "Pas d'application du téléphone sur ce serveur.")
    return path


def _build(folder: Path) -> int | None:
    try:
        build = json.loads((folder / CARD).read_text(encoding="utf-8")).get("build")
    except (OSError, ValueError, AttributeError):
        return None
    return build if isinstance(build, int) and not isinstance(build, bool) and build > 0 else None


@router.get("/latest")
async def latest_app(settings: AppSettings) -> AppVersionOut:
    """La version de l'application que ce serveur peut donner au téléphone."""
    apk = _apk(settings.phone_app_dir)
    return AppVersionOut(build=_build(apk.parent), size=apk.stat().st_size, url=f"/v1/app/{APK}")


@router.get(f"/{APK}", response_class=FileResponse)
async def download_app(settings: AppSettings) -> FileResponse:
    return FileResponse(_apk(settings.phone_app_dir), media_type=APK_TYPE, filename=APK)
