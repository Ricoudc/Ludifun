"""Figures des cartes et du coloriage (étape 22) : publiques, mises en cache par l'application."""

from httpx import AsyncClient


async def test_figure_is_served_with_its_zones(client: AsyncClient) -> None:
    r = await client.get("/v1/figures/france-regions")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=604800"
    figure = r.json()
    assert figure["id"] == "france-regions" and figure["version"] == 1
    assert "Bretagne" in {z["name"] for z in figure["zones"]}


async def test_unknown_figure(client: AsyncClient) -> None:
    for figure_id in ("atlantide", "..%2F..%2Fpyproject.toml"):
        r = await client.get(f"/v1/figures/{figure_id}")
        assert r.status_code == 404
