"""Ce que le code sait du français, pour fabriquer des jeux justes sans IA : conjuguer les verbes
courants, des phrases à trous sur les homophones, un petit lexique (nature des mots, singulier et
pluriel, masculin et féminin). Tout est écrit ici à la main ou calculé par des règles sûres :
aucune réponse n'est devinée.

Les verbes retenus sont réguliers (1er groupe sans changement de radical, 2e groupe) ou appris
par cœur (être, avoir, aller, faire). Au passé composé, seulement l'auxiliaire avoir : avec
être, l'accord dépendrait de qui parle.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from app.domain.text import normalize

PERSONS = ("je", "tu", "il", "nous", "vous", "ils")


class Tense(StrEnum):
    PRESENT = "présent"
    FUTUR = "futur"
    IMPARFAIT = "imparfait"
    PASSE_COMPOSE = "passé composé"


FIRST_GROUP = (
    "chanter", "jouer", "parler", "danser", "regarder", "manger", "nager", "ranger", "commencer",
    "lancer", "dessiner", "travailler", "écouter", "aimer", "marcher", "sauter", "porter", "laver",
)  # fmt: skip
SECOND_GROUP = ("finir", "choisir", "grandir", "remplir", "réussir", "obéir")
IRREGULAR: dict[str, dict[Tense, tuple[str, ...]]] = {
    "être": {
        Tense.PRESENT: ("suis", "es", "est", "sommes", "êtes", "sont"),
        Tense.IMPARFAIT: ("étais", "étais", "était", "étions", "étiez", "étaient"),
        Tense.FUTUR: ("serai", "seras", "sera", "serons", "serez", "seront"),
        Tense.PASSE_COMPOSE: ("ai été", "as été", "a été", "avons été", "avez été", "ont été"),
    },
    "avoir": {
        Tense.PRESENT: ("ai", "as", "a", "avons", "avez", "ont"),
        Tense.IMPARFAIT: ("avais", "avais", "avait", "avions", "aviez", "avaient"),
        Tense.FUTUR: ("aurai", "auras", "aura", "aurons", "aurez", "auront"),
        Tense.PASSE_COMPOSE: ("ai eu", "as eu", "a eu", "avons eu", "avez eu", "ont eu"),
    },
    "aller": {
        Tense.PRESENT: ("vais", "vas", "va", "allons", "allez", "vont"),
        Tense.IMPARFAIT: ("allais", "allais", "allait", "allions", "alliez", "allaient"),
        Tense.FUTUR: ("irai", "iras", "ira", "irons", "irez", "iront"),
    },
    "faire": {
        Tense.PRESENT: ("fais", "fais", "fait", "faisons", "faites", "font"),
        Tense.IMPARFAIT: ("faisais", "faisais", "faisait", "faisions", "faisiez", "faisaient"),
        Tense.FUTUR: ("ferai", "feras", "fera", "ferons", "ferez", "feront"),
        Tense.PASSE_COMPOSE: ("ai fait", "as fait", "a fait", "avons fait", "avez fait", "ont fait"),
    },
}
AVOIR_PRESENT = IRREGULAR["avoir"][Tense.PRESENT]


def _soft(stem: str, ending: str) -> str:
    """manger → mangeons, commencer → commençons : le son reste doux devant a et o."""
    if ending[:1] in ("a", "o"):
        if stem.endswith("g"):
            return stem + "e" + ending
        if stem.endswith("c"):
            return stem[:-1] + "ç" + ending
    return stem + ending


def conjugate(verb: str, tense: Tense) -> tuple[str, ...] | None:
    """Les six formes (je, tu, il, nous, vous, ils), ou None pour un verbe ou un temps inconnu."""
    if verb in IRREGULAR:
        return IRREGULAR[verb].get(tense)
    if verb in FIRST_GROUP:
        stem = verb[:-2]
        if tense is Tense.PRESENT:
            return tuple(_soft(stem, e) for e in ("e", "es", "e", "ons", "ez", "ent"))
        if tense is Tense.IMPARFAIT:
            return tuple(_soft(stem, e) for e in ("ais", "ais", "ait", "ions", "iez", "aient"))
        if tense is Tense.FUTUR:
            return tuple(verb + e for e in ("ai", "as", "a", "ons", "ez", "ont"))
        return tuple(f"{a} {stem}é" for a in AVOIR_PRESENT)
    if verb in SECOND_GROUP:
        stem = verb[:-2]
        if tense is Tense.PRESENT:
            return tuple(stem + e for e in ("is", "is", "it", "issons", "issez", "issent"))
        if tense is Tense.IMPARFAIT:
            return tuple(stem + e for e in ("issais", "issais", "issait", "issions", "issiez", "issaient"))
        if tense is Tense.FUTUR:
            return tuple(verb + e for e in ("ai", "as", "a", "ons", "ez", "ont"))
        return tuple(f"{a} {stem}i" for a in AVOIR_PRESENT)
    return None


def pronoun(person: int, form: str) -> str:
    """« je » devient « j' » devant une voyelle : j'aime, j'ai, j'étais."""
    if person == 0 and form[:1] in "aeéèêiouh":
        return "j'"
    return PERSONS[person]


# --------------------------------------------------------------------------- #
# Quels thèmes de français la notion travaille-t-elle ?
# --------------------------------------------------------------------------- #


class FrenchTopic(StrEnum):
    CONJUGATION = "conjugaison"
    HOMOPHONES = "homophones"
    NATURE = "nature des mots"
    NUMBER = "singulier et pluriel"
    GENDER = "masculin et féminin"
    ALPHABET = "ordre alphabétique"


_TOPICS = (
    (
        FrenchTopic.CONJUGATION,
        r"conjug|present de l indicatif|\bfutur\b|imparfait|passe compose|groupe des verbes"
        r"|verbes? du (1er|2e|premier|deuxieme) groupe",
    ),
    (FrenchTopic.HOMOPHONES, r"homophone"),
    (
        FrenchTopic.NATURE,
        r"nature des mots|classe grammaticale|\bdeterminants?\b|\badjectifs?\b|\bnoms? (communs?|propres?)\b",
    ),
    (FrenchTopic.NUMBER, r"\bpluriel|\bsingulier"),
    (FrenchTopic.GENDER, r"\bfeminin|\bmasculin"),
    (FrenchTopic.ALPHABET, r"ordre alphabetique|\balphabet\b|\bdictionnaire"),
)


def french_topics(text: str) -> list[FrenchTopic]:
    found = [topic for topic, pattern in _TOPICS if re.search(pattern, normalize(text))]
    if FrenchTopic.HOMOPHONES not in found and homophone_pairs(text):
        found.append(FrenchTopic.HOMOPHONES)
    return found


def tense_of(text: str) -> Tense:
    plain = normalize(text)
    for tense, pattern in (
        (Tense.PASSE_COMPOSE, "passe compose"),
        (Tense.IMPARFAIT, "imparfait"),
        (Tense.FUTUR, "futur"),
    ):
        if pattern in plain:
            return tense
    return Tense.PRESENT


def verbs_of(text: str, tense: Tense) -> list[str]:
    """Les verbes à conjuguer : ceux que nomme la notion, sinon ceux de son groupe, sinon tous."""
    words = set(re.findall(r"[a-zàâçéèêëîïôûùü]+", text.lower()))
    known = [v for v in (*IRREGULAR, *FIRST_GROUP, *SECOND_GROUP) if conjugate(v, tense)]
    named = [v for v in known if v in words]
    if named:
        return named
    plain = normalize(text)
    if re.search(r"(2e|deuxieme) groupe", plain):
        return list(SECOND_GROUP)
    if re.search(r"(1er|premier) groupe", plain):
        return [v for v in FIRST_GROUP if conjugate(v, tense)]
    return known


# --------------------------------------------------------------------------- #
# Homophones : des phrases écrites ici, la bonne réponse connue
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Blank:
    sentence: str  # avec « ___ » à la place du mot
    answer: str


HOMOPHONES: dict[tuple[str, str], tuple[Blank, ...]] = {
    ("a", "à"): (
        Blank("Léa ___ un chat noir.", "a"),
        Blank("Nous allons ___ la piscine.", "à"),
        Blank("Il ___ faim ce matin.", "a"),
        Blank("Je suis ___ l'école.", "à"),
        Blank("Tom ___ perdu sa balle.", "a"),
        Blank("Le gâteau ___ la fraise est délicieux.", "à"),
        Blank("Mon frère ___ une nouvelle trousse.", "a"),
        Blank("Papa rentre ___ six heures.", "à"),
    ),
    ("et", "est"): (
        Blank("Le ciel ___ bleu.", "est"),
        Blank("J'aime les pommes ___ les poires.", "et"),
        Blank("Paul ___ malade aujourd'hui.", "est"),
        Blank("Le chat ___ le chien dorment.", "et"),
        Blank("La soupe ___ chaude.", "est"),
        Blank("Elle chante ___ elle danse.", "et"),
        Blank("Ce livre ___ passionnant.", "est"),
        Blank("Marie ___ Hugo jouent ensemble.", "et"),
    ),
    ("son", "sont"): (
        Blank("Les enfants ___ dans la cour.", "sont"),
        Blank("Lucas range ___ cartable.", "son"),
        Blank("Mes amis ___ gentils.", "sont"),
        Blank("Elle promène ___ chien.", "son"),
        Blank("Les fleurs ___ jolies.", "sont"),
        Blank("Il a perdu ___ bonnet.", "son"),
    ),
    ("on", "ont"): (
        Blank("Les élèves ___ fini leur travail.", "ont"),
        Blank("Demain, ___ va au parc.", "on"),
        Blank("Mes cousins ___ un chien.", "ont"),
        Blank("Ce soir, ___ mange des crêpes.", "on"),
        Blank("Les oiseaux ___ construit un nid.", "ont"),
        Blank("À la plage, ___ ramasse des coquillages.", "on"),
    ),
    ("ces", "ses"): (
        Blank("Regarde ___ beaux nuages !", "ces"),
        Blank("Léo prête ___ crayons à Nina.", "ses"),
        Blank("Je n'aime pas ___ chaussures-là.", "ces"),
        Blank("Elle range ___ jouets dans sa chambre.", "ses"),
        Blank("Tom joue avec ___ amis.", "ses"),
        Blank("Tu vois ___ montagnes au loin ?", "ces"),
    ),
    ("ou", "où"): (
        Blank("Veux-tu du lait ___ du jus ?", "ou"),
        Blank("Dis-moi ___ tu habites.", "où"),
        Blank("Je ne sais pas ___ est mon stylo.", "où"),
        Blank("Tu préfères le rouge ___ le bleu ?", "ou"),
        Blank("C'est la ville ___ vit ma tante.", "où"),
        Blank("On ira au cinéma ___ au musée.", "ou"),
    ),
    ("ce", "se"): (
        Blank("Il ___ lave les mains.", "se"),
        Blank("J'aime ___ dessin.", "ce"),
        Blank("Les chats ___ cachent sous le lit.", "se"),
        Blank("Regarde ___ chien !", "ce"),
        Blank("Elle ___ brosse les dents.", "se"),
        Blank("Je voudrais ___ livre.", "ce"),
    ),
}
EARLY_PAIRS = (("a", "à"), ("et", "est"), ("son", "sont"), ("on", "ont"))  # CP-CE1


def homophone_pairs(text: str) -> list[tuple[str, str]]:
    """Les paires que la notion nomme (« a / à », « et ou est ») ; toutes si elle parle
    d'homophones sans en nommer."""
    lower = " " + text.lower().replace("’", "'") + " "
    named = []
    for first, second in HOMOPHONES:
        for x, y in ((first, second), (second, first)):
            if re.search(rf"(?<![\w']){re.escape(x)}\s*(?:/|ou|,|et)\s*{re.escape(y)}(?!\w)", lower):
                named.append((first, second))
                break
    if named:
        return named
    return list(HOMOPHONES) if "homophone" in normalize(text) else []


# --------------------------------------------------------------------------- #
# Petit lexique : des mots dont la nature, le nombre et le genre sont sûrs
# --------------------------------------------------------------------------- #

LEXICON: dict[FrenchTopic, dict[str, tuple[str, ...]]] = {
    FrenchTopic.NATURE: {
        "noms": (
            "chat",
            "maison",
            "école",
            "arbre",
            "voiture",
            "jardin",
            "livre",
            "soleil",
            "fleur",
            "pomme",
            "cahier",
            "oiseau",
        ),
        "verbes": (
            "courir",
            "manger",
            "chanter",
            "dormir",
            "lire",
            "sauter",
            "finir",
            "jouer",
            "écrire",
            "partir",
        ),
        "adjectifs": (
            "grand",
            "petit",
            "rouge",
            "joli",
            "rapide",
            "gentil",
            "froid",
            "heureux",
            "calme",
            "rond",
        ),
        "déterminants": ("le", "la", "les", "un", "une", "des", "mon", "ta", "ces", "leur"),
    },
    FrenchTopic.NUMBER: {
        "au singulier": (
            "le chat",
            "une fleur",
            "mon livre",
            "la voiture",
            "un oiseau",
            "ce jardin",
            "le cheval",
            "un journal",
        ),
        "au pluriel": (
            "les chats",
            "des fleurs",
            "mes livres",
            "les voitures",
            "des oiseaux",
            "ces jardins",
            "les chevaux",
            "des journaux",
        ),
    },
    FrenchTopic.GENDER: {
        "au masculin": (
            "un lion",
            "le boulanger",
            "un chanteur",
            "le cousin",
            "un ami",
            "le roi",
            "un acteur",
            "le voisin",
        ),
        "au féminin": (
            "une lionne",
            "la boulangère",
            "une chanteuse",
            "la cousine",
            "une amie",
            "la reine",
            "une actrice",
            "la voisine",
        ),
    },
}

# Mots à ranger dans l'ordre alphabétique : courants, sans trait d'union, tous différents une
# fois les accents retirés (l'ordre du dictionnaire ne tient pas compte des accents).
ALPHABET_WORDS = (
    "abeille", "arbre", "avion", "ballon", "banane", "bateau", "bonbon", "cahier", "camion",
    "carotte", "chat", "cheval", "citron", "dauphin", "dent", "domino", "école", "éléphant",
    "étoile", "fleur", "forêt", "fusée", "gâteau", "girafe", "gomme", "hibou", "igloo", "jardin",
    "journal", "kiwi", "lapin", "livre", "lune", "maison", "montagne", "moto", "nuage", "orange",
    "ours", "papillon", "pomme", "poule", "quille", "renard", "robot", "rose", "sapin", "soleil",
    "souris", "tigre", "tortue", "train", "usine", "vache", "vélo", "violon", "wagon", "yaourt",
    "zèbre",
)  # fmt: skip
