"""Le vocabulaire d'anglais de l'école, en images (spécification technique §5.62).

Une banque écrite à la main, par thème : le mot anglais, sa traduction et son image (émoji ; pas
d'image pour les jours et les mois, montrés en français). Le téléphone prononce le mot anglais.

Domaine pur : pas de base, pas de réseau.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from app.domain.text import normalize


class EnglishTheme(StrEnum):
    COLOURS = "colours"
    NUMBERS = "numbers"
    DAYS = "days"
    MONTHS = "months"
    ANIMALS = "animals"
    FOOD = "food"
    BODY = "body"
    SCHOOL = "school"
    WEATHER = "weather"
    CLOTHES = "clothes"


@dataclass(frozen=True)
class EnglishWord:
    english: str
    french: str
    theme: EnglishTheme
    picture: str | None = None


def _theme(theme: EnglishTheme, *words: tuple[str, str, str | None]) -> list[EnglishWord]:
    return [EnglishWord(english, french, theme, picture) for english, french, picture in words]


T = EnglishTheme
ENGLISH_WORDS: tuple[EnglishWord, ...] = (
    *_theme(
        T.COLOURS,
        ("red", "rouge", "🟥"),
        ("blue", "bleu", "🟦"),
        ("green", "vert", "🟩"),
        ("yellow", "jaune", "🟨"),
        ("orange", "orange", "🟧"),
        ("purple", "violet", "🟪"),
        ("black", "noir", "⬛"),
        ("white", "blanc", "⬜"),
        ("brown", "marron", "🟫"),
    ),
    *_theme(
        T.NUMBERS,
        ("one", "un", "1️⃣"),
        ("two", "deux", "2️⃣"),
        ("three", "trois", "3️⃣"),
        ("four", "quatre", "4️⃣"),
        ("five", "cinq", "5️⃣"),
        ("six", "six", "6️⃣"),
        ("seven", "sept", "7️⃣"),
        ("eight", "huit", "8️⃣"),
        ("nine", "neuf", "9️⃣"),
        ("ten", "dix", "🔟"),
    ),
    *_theme(
        T.DAYS,
        ("Monday", "lundi", None),
        ("Tuesday", "mardi", None),
        ("Wednesday", "mercredi", None),
        ("Thursday", "jeudi", None),
        ("Friday", "vendredi", None),
        ("Saturday", "samedi", None),
        ("Sunday", "dimanche", None),
    ),
    *_theme(
        T.MONTHS,
        ("January", "janvier", None),
        ("February", "février", None),
        ("March", "mars", None),
        ("April", "avril", None),
        ("May", "mai", None),
        ("June", "juin", None),
        ("July", "juillet", None),
        ("August", "août", None),
        ("September", "septembre", None),
        ("October", "octobre", None),
        ("November", "novembre", None),
        ("December", "décembre", None),
    ),
    *_theme(
        T.ANIMALS,
        ("dog", "le chien", "🐶"),
        ("cat", "le chat", "🐱"),
        ("bird", "l'oiseau", "🐦"),
        ("fish", "le poisson", "🐟"),
        ("horse", "le cheval", "🐴"),
        ("cow", "la vache", "🐮"),
        ("pig", "le cochon", "🐷"),
        ("mouse", "la souris", "🐭"),
        ("rabbit", "le lapin", "🐰"),
        ("duck", "le canard", "🦆"),
        ("frog", "la grenouille", "🐸"),
    ),
    *_theme(
        T.FOOD,
        ("apple", "la pomme", "🍎"),
        ("banana", "la banane", "🍌"),
        ("bread", "le pain", "🍞"),
        ("cheese", "le fromage", "🧀"),
        ("milk", "le lait", "🥛"),
        ("egg", "l'œuf", "🥚"),
        ("cake", "le gâteau", "🍰"),
        ("carrot", "la carotte", "🥕"),
        ("strawberry", "la fraise", "🍓"),
    ),
    *_theme(
        T.BODY,
        ("eye", "l'œil", "👁️"),
        ("nose", "le nez", "👃"),
        ("mouth", "la bouche", "👄"),
        ("ear", "l'oreille", "👂"),
        ("hand", "la main", "✋"),
        ("foot", "le pied", "🦶"),
        ("leg", "la jambe", "🦵"),
        ("tooth", "la dent", "🦷"),
    ),
    *_theme(
        T.SCHOOL,
        ("pencil", "le crayon", "✏️"),
        ("book", "le livre", "📕"),
        ("scissors", "les ciseaux", "✂️"),
        ("schoolbag", "le cartable", "🎒"),
        ("ruler", "la règle", "📏"),
        ("pen", "le stylo", "🖊️"),
    ),
    *_theme(
        T.WEATHER,
        ("sun", "le soleil", "☀️"),
        ("rain", "la pluie", "🌧️"),
        ("snow", "la neige", "❄️"),
        ("cloud", "le nuage", "☁️"),
        ("wind", "le vent", "💨"),
        ("rainbow", "l'arc-en-ciel", "🌈"),
    ),
    *_theme(
        T.CLOTHES,
        ("T-shirt", "le tee-shirt", "👕"),
        ("trousers", "le pantalon", "👖"),
        ("dress", "la robe", "👗"),
        ("shoes", "les chaussures", "👟"),
        ("cap", "la casquette", "🧢"),
        ("socks", "les chaussettes", "🧦"),
        ("coat", "le manteau", "🧥"),
    ),
)

# Ce que dit une leçon d'anglais (en anglais ou en français) de son thème.
_THEMES: tuple[tuple[EnglishTheme, str], ...] = (
    (T.COLOURS, r"\bcolou?rs?\b|\bcouleurs?\b"),
    (T.NUMBERS, r"\bnumbers?\b|\bnombres?\b|\bchiffres?\b|\bcount(?:ing)?\b|\bcompter\b"),
    (T.DAYS, r"\bdays?\b|\bjours de la semaine\b|\bweek\b"),
    (T.MONTHS, r"\bmonths?\b|\bmois\b"),
    (T.ANIMALS, r"\banimals?\b|\banimaux\b|\bpets?\b"),
    (T.FOOD, r"\bfood\b|\bfruits?\b|\bnourriture\b|\baliments?\b|\bbreakfast\b|\bvegetables?\b"),
    (T.BODY, r"\bbody\b|\bparties du corps\b"),
    (T.SCHOOL, r"\bschool ?bag\b|\bclassroom\b|\bschool things\b|\bfournitures?\b|\bmateriel scolaire\b"),
    (T.WEATHER, r"\bweather\b|\bmeteo\b"),
    (T.CLOTHES, r"\bclothes\b|\bvetements?\b"),
)
MIN_NAMED = 2  # deux mots de la banque nomment un thème (« red, blue, green »)


def _named(text: str) -> list[EnglishWord]:
    """Les mots de la banque écrits dans la leçon (« dog », « Monday »), dans l'ordre de la banque."""
    words = set(re.findall(r"[a-z]+(?:-[a-z]+)?", text.lower()))
    return [w for w in ENGLISH_WORDS if w.english.lower() in words]


def english_themes(text: str) -> list[EnglishTheme]:
    """Les thèmes de vocabulaire d'une leçon d'anglais : ceux qu'elle nomme, puis ceux dont elle
    écrit au moins deux mots."""
    plain = normalize(text)
    found = [theme for theme, pattern in _THEMES if re.search(pattern, plain)]
    named = _named(text)
    for theme in EnglishTheme:
        if theme not in found and sum(w.theme == theme for w in named) >= MIN_NAMED:
            found.append(theme)
    return found


def lesson_words(text: str) -> list[EnglishWord]:
    """Les mots de la banque que la leçon écrit : ils passent d'abord (§5.58)."""
    return _named(text)


def words_of(theme: EnglishTheme) -> list[EnglishWord]:
    return [w for w in ENGLISH_WORDS if w.theme == theme]
