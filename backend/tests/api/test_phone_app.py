"""§5.50 : le serveur de la maison donne au téléphone la dernière application de test."""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.config import Settings

APK = b"PK\x03\x04 application de test" * 100


def serve(app: FastAPI, folder: Path | None) -> None:
    settings: Settings = app.state.settings
    app.state.settings = settings.model_copy(update={"phone_app_dir": folder})


async def test_latest_version_and_download(app: FastAPI, client: AsyncClient, tmp_path: Path) -> None:
    (tmp_path / "ludifun.apk").write_bytes(APK)
    (tmp_path / "ludifun.json").write_text(json.dumps({"build": 412, "commit": "abc"}), encoding="utf-8")
    serve(app, tmp_path)
    latest = await client.get("/v1/app/latest")  # sans jeton : l'application n'est pas secrète
    assert latest.status_code == 200
    assert latest.json() == {"build": 412, "size": len(APK), "url": "/v1/app/ludifun.apk"}
    download = await client.get(latest.json()["url"])
    assert download.status_code == 200 and download.content == APK
    assert download.headers["content-type"] == "application/vnd.android.package-archive"
    assert 'filename="ludifun.apk"' in download.headers["content-disposition"]


@pytest.mark.parametrize("card", [None, "pas du json", '{"build": "412"}', '{"build": true}', "[1]"])
async def test_unknown_build(app: FastAPI, client: AsyncClient, tmp_path: Path, card: str | None) -> None:
    (tmp_path / "ludifun.apk").write_bytes(APK)
    if card is not None:
        (tmp_path / "ludifun.json").write_text(card, encoding="utf-8")
    serve(app, tmp_path)
    assert (await client.get("/v1/app/latest")).json()["build"] is None


async def test_no_app_to_give(app: FastAPI, client: AsyncClient, tmp_path: Path) -> None:
    for folder in (None, tmp_path, tmp_path / "absent"):
        serve(app, folder)
        for url in ("/v1/app/latest", "/v1/app/ludifun.apk"):
            r = await client.get(url)
            assert r.status_code == 404 and r.json()["error"]["code"] == "no_phone_app"
    # Pas d'autre fichier du dossier servi.
    (tmp_path / "secret.txt").write_text("x", encoding="utf-8")
    serve(app, tmp_path)
    assert (await client.get("/v1/app/secret.txt")).status_code == 404
    assert (await client.get("/v1/app/..%2Fsecret.txt")).status_code == 404
