"""Les sons du CP et du CE1 : ou, on, an, in, oi (spécification technique §5.62).

Une banque écrite à la main : chaque mot a son image (émoji), le son étudié et la façon dont il
s'écrit dans ce mot (« serpent » : le son an écrit « en »). Le jeu cache ces lettres
(« serp__t ») et l'enfant choisit les bonnes.

Règle de la banque, vérifiée mot par mot : remplacer les lettres cachées par celles d'un autre
son du jeu ne forme jamais un autre vrai mot (« m__che » avec « an » donnerait « manche » :
« mouche » n'est donc pas dans la banque). `graphies_only` : un mot qui n'est sûr qu'entre les
écritures d'un même son (« d__t » donnerait « dont » avec « on », mais « dant », « damt »,
« demt » n'existent pas).

Domaine pur : pas de base, pas de réseau.
"""

import re
from dataclasses import dataclass

from app.domain.text import normalize

SOUNDS = ("ou", "on", "an", "in", "oi")
# Les écritures de chaque son (les plus courantes d'abord).
GRAPHIES: dict[str, tuple[str, ...]] = {
    "ou": ("ou",),
    "on": ("on", "om"),
    "an": ("an", "en", "am", "em"),
    "in": ("in", "ain", "im", "ein"),
    "oi": ("oi",),
}
SOUND_OF = {graphy: sound for sound, graphies in GRAPHIES.items() for graphy in graphies}
# Les confusions classiques, quand la leçon n'étudie qu'un son : ou/on, on/an, in/an, oi/ou.
CONFUSABLE: dict[str, tuple[str, ...]] = {
    "ou": ("on", "oi", "an"),
    "on": ("ou", "an", "in"),
    "an": ("on", "in", "ou"),
    "in": ("an", "on", "oi"),
    "oi": ("ou", "on", "in"),
}


@dataclass(frozen=True)
class SoundWord:
    word: str
    picture: str  # émoji : l'enfant qui lit encore mal reconnaît le mot
    sound: str
    graphy: str  # les lettres du son dans ce mot (cachées par le jeu)
    graphies_only: bool = False  # sûr seulement entre les écritures d'un même son

    @property
    def masked(self) -> str:
        """« loup » → « l__p » (la première fois que les lettres du son apparaissent)."""
        return self.word.replace(self.graphy, "__", 1)

    def with_letters(self, letters: str) -> str:
        return self.word.replace(self.graphy, letters, 1)


def _w(word: str, picture: str, sound: str, graphy: str | None = None, only: bool = False) -> SoundWord:
    return SoundWord(word, picture, sound, graphy or sound, only)


SOUND_WORDS: tuple[SoundWord, ...] = (
    # ou
    _w("loup", "🐺", "ou"),
    _w("poule", "🐔", "ou"),
    _w("bouche", "👄", "ou"),
    _w("souris", "🐭", "ou"),
    _w("mouton", "🐑", "ou"),
    _w("hibou", "🦉", "ou"),
    _w("fourchette", "🍴", "ou"),
    _w("poussin", "🐤", "ou"),
    # on
    _w("ballon", "🎈", "on"),
    _w("lion", "🦁", "on"),
    _w("camion", "🚚", "on"),
    _w("bonbon", "🍬", "on"),
    _w("biberon", "🍼", "on"),
    _w("avion", "✈️", "on"),
    _w("dragon", "🐉", "on"),
    _w("melon", "🍈", "on"),
    _w("pompier", "🚒", "on", "om"),
    _w("trompette", "🎺", "on", "om"),
    # an
    _w("éléphant", "🐘", "an"),
    _w("pantalon", "👖", "an"),
    _w("banane", "🍌", "an"),
    _w("kangourou", "🦘", "an"),
    _w("manteau", "🧥", "an"),
    _w("ange", "👼", "an"),
    _w("serpent", "🐍", "an", "en"),
    _w("tambour", "🥁", "an", "am"),
    _w("jambe", "🦵", "an", "am"),
    _w("dent", "🦷", "an", "en", only=True),
    _w("tempête", "🌪️", "an", "em"),
    # in
    _w("pingouin", "🐧", "in"),
    _w("dauphin", "🐬", "in"),
    _w("requin", "🦈", "in"),
    _w("lutin", "🧝", "in"),
    _w("cinq", "5️⃣", "in"),
    _w("lapin", "🐰", "in", only=True),
    _w("main", "✋", "in", "ain", only=True),
    _w("train", "🚂", "in", "ain", only=True),
    _w("peinture", "🎨", "in", "ein"),
    _w("imprimante", "🖨️", "in", "im", only=True),
    # oi
    _w("roi", "👑", "oi"),
    _w("oiseau", "🐦", "oi"),
    _w("étoile", "⭐", "oi"),
    _w("poisson", "🐟", "oi"),
    _w("voiture", "🚗", "oi"),
    _w("poire", "🍐", "oi"),
)

# « le son ou », « les sons on et an », « j'entends in », « le son [an] » (crochets retirés).
_NAMED = re.compile(
    r"\b(?:sons?|j entends|on entend)\b((?:\s+(?:et|ou|on|an|en|am|em|om|in|im|ain|ein|oi)\b)+)"
)


def lesson_sounds(text: str) -> list[str]:
    """Les sons nommés par la leçon (« Les sons an et en » → ["an"]), dans l'ordre."""
    found: list[str] = []
    for group in _NAMED.findall(normalize(text.replace("/", " "))):
        for word in group.split():
            sound = SOUND_OF.get(word)
            if sound is not None and sound not in found:
                found.append(sound)
    return found


def words_of(sound: str) -> list[SoundWord]:
    return [w for w in SOUND_WORDS if w.sound == sound]
