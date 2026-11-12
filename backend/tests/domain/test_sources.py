"""Étape 24 : ce que le code décide dans la recherche de sources (sites, extraits, citations)."""

from app.domain.sources import (
    DEFAULT_SITES,
    Excerpt,
    Quote,
    allowed,
    best_excerpts,
    check_answer,
    passages,
)

VIKIDIA = "https://fr.vikidia.org/wiki/%C3%89tats_g%C3%A9n%C3%A9raux_de_1789"
PAGE = (
    "États généraux de 1789\n\n"
    "Les États généraux de 1789 sont une assemblée réunie par le roi Louis XVI à Versailles, "
    "le 5 mai 1789, pour trouver de l'argent car le royaume est en crise financière.\n\n"
    "Ils rassemblent des députés des trois ordres : le clergé, la noblesse et le tiers état. "
    "Le tiers état représente la très grande majorité des Français.\n\n"
    "Le 17 juin 1789, les députés du tiers état se proclament Assemblée nationale."
)


def test_only_https_pages_of_allowed_sites() -> None:
    assert allowed(VIKIDIA, DEFAULT_SITES)
    assert allowed("https://fr.m.wikipedia.org/wiki/Volcan", ["wikipedia.org"])  # sous-domaine
    assert not allowed("http://fr.vikidia.org/wiki/Volcan", DEFAULT_SITES)  # pas en https
    assert not allowed("https://fr.vikidia.org.pirate.example/wiki", DEFAULT_SITES)
    assert not allowed("https://evilfr.vikidia.org/wiki", ["fr.vikidia.org"])
    assert not allowed("https://forum-devoirs.example/1789", DEFAULT_SITES)


def test_pages_become_short_passages() -> None:
    chunks = passages(PAGE, max_chars=200)
    assert chunks[0].startswith("États généraux de 1789 Les États généraux")  # titre rattaché
    assert all(len(c) <= 200 for c in chunks)
    long = "Une phrase assez longue pour compter. " * 30
    assert all(len(c) <= 200 and c.endswith(".") for c in passages(long, max_chars=200))


def test_best_excerpts_match_the_question_and_vary_the_sources() -> None:
    other = (
        "https://fr.wikipedia.org/wiki/Tiers_%C3%A9tat",
        "Tiers état",
        "Le tiers état désigne la très grande majorité des Français du royaume. " * 3,
    )
    pages = [(VIKIDIA, "États généraux", PAGE), other]
    chosen = best_excerpts("Qui compose le tiers état aux États généraux ?", pages, count=3, max_chars=200)
    assert [e.number for e in chosen] == [1, 2, 3]
    assert sum(1 for e in chosen if e.url == VIKIDIA) <= 2
    assert any(e.site == "fr.wikipedia.org" for e in chosen)
    assert best_excerpts("photosynthèse chlorophylle", pages) == []


def excerpt() -> Excerpt:
    return Excerpt(1, VIKIDIA, "États généraux", passages(PAGE)[0])


def test_an_answer_is_kept_only_with_a_verified_quote() -> None:
    real = Quote(1, "une assemblée réunie par le roi Louis XVI à Versailles")
    kept = check_answer("Le roi les réunit pour trouver de l'argent.", [real], [excerpt()], found=True)
    assert kept is not None and kept.sources == [excerpt()] and kept.origin == "SOURCE_EXTERNAL_KNOWLEDGE"
    # Citation inventée, trop courte, ou d'une source qui n'existe pas : écartée.
    invented = Quote(1, "Louis XVI voulait aussi construire un château")
    assert check_answer("…", [invented], [excerpt()], found=True) is None
    assert check_answer("Réponse.", [Quote(1, "le 5 mai")], [excerpt()], found=True) is None
    assert check_answer("Réponse.", [Quote(4, real.text)], [excerpt()], found=True) is None
    # L'IA dit ne pas avoir trouvé : rien n'est montré, même avec une citation juste.
    assert check_answer("Réponse.", [real], [excerpt()], found=False) is None
    assert check_answer("x" * 700, [real], [excerpt()], found=True) is None
    # Une citation sur deux vérifiée : seule la vérifiée est gardée.
    both = check_answer("Réponse.", [real, invented], [excerpt()], found=True)
    assert both is not None and both.quotes == [Quote(1, real.text)]


def test_menus_are_skipped_and_causes_answer_why() -> None:
    """Essai réel du 28/09 : un bout de menu de Lumni choisi, et aucun extrait sur la cause."""
    lumni = (
        "https://www.lumni.fr/video/etats-generaux",
        "Lumni",
        "-> En savoir plus Histoire05:52Publié le 25/11/2025 Face à la crise, Louis XVI convoque les "
        "États généraux en 1789",
    )
    vikidia = (
        VIKIDIA,
        "États généraux",
        "Les États généraux sont convoqués pour la dernière fois en 1789, par Louis XVI.\n\n"
        "Le royaume est endetté : pour trouver de l'argent, Louis XVI réunit les États généraux "
        "afin de voter de nouveaux impôts.",
    )
    chosen = best_excerpts("Pourquoi Louis XVI réunit-il les États généraux ?", [vikidia, lumni], count=2)
    assert all("En savoir plus" not in e.text for e in chosen)
    assert "endetté" in chosen[0].text
