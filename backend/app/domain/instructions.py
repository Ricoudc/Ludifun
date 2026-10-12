"""Consignes adaptées à la classe de l'enfant (étape 25).

Trois registres, un par cycle : cycle 2 (CP, CE1, CE2) des phrases très courtes et concrètes, à
lire seul ; cycle 3 (CM1, CM2, 6e) un peu plus de précision ; cycle 4 (5e, 4e, 3e) un ton plus
scolaire. La consigne dit comment jouer ; la question, elle, vient du matériel de la leçon.

Les règles d'écriture (`writing_rules`) sont données à l'IA qui prépare le matériel : elle écrit
les questions au niveau de l'enfant. Le code, lui, ne dépend pas de ce qu'elle en fait.
"""

from app.domain.activities.base import ActivityCode
from app.domain.knowledge import Grade

CYCLES: dict[Grade, int] = {
    Grade.CP: 2,
    Grade.CE1: 2,
    Grade.CE2: 2,
    Grade.CM1: 3,
    Grade.CM2: 3,
    Grade.SIXIEME: 3,
    Grade.CINQUIEME: 4,
    Grade.QUATRIEME: 4,
    Grade.TROISIEME: 4,
}

# Pour chaque jeu : consigne du cycle 2, du cycle 3, du cycle 4.
_TEXTS: dict[ActivityCode, tuple[str, str, str]] = {
    ActivityCode.MCQ: (
        "Lis la question. Touche la bonne réponse.",
        "Lis la question, puis choisis la bonne réponse parmi les quatre.",
        "Choisis la réponse exacte parmi les quatre propositions.",
    ),
    ActivityCode.TRUE_FALSE: (
        "Lis la phrase. Est-ce vrai ou faux ?",
        "Lis la phrase et dis si elle est vraie ou fausse.",
        "Indique si l'affirmation est vraie ou fausse.",
    ),
    ActivityCode.FILL_BLANK: (
        "Il manque un mot. Écris-le.",
        "Écris le mot qui manque dans la phrase.",
        "Complète la phrase avec le terme exact.",
    ),
    ActivityCode.MATCH: (
        "Touche un mot, puis touche ce qui va avec.",
        "Relie chaque élément de gauche à celui qui lui correspond à droite.",
        "Associe chaque élément à sa correspondance.",
    ),
    ActivityCode.SPEED_CHALLENGE: (
        "Vite ! Vrai ou faux ?",
        "Réponds vrai ou faux le plus vite possible.",
        "Vrai ou faux : réponds avant la fin du temps.",
    ),
    ActivityCode.FLASHCARD: (
        "Lis la carte. Tu sais ? Retourne-la pour voir.",
        "Essaie de te souvenir de la réponse, puis retourne la carte pour vérifier.",
        "Récite la réponse de mémoire, puis retourne la carte et sois honnête.",
    ),
    ActivityCode.OPEN_QUESTION: (
        "Réponds avec tes mots. Une phrase suffit.",
        "Réponds en une ou deux phrases, avec tes mots.",
        "Rédige une réponse courte et précise, en une ou deux phrases.",
    ),
    ActivityCode.ORDER: (
        "Touche les étiquettes une par une, dans l'ordre demandé.",
        "Touche les étiquettes dans l'ordre, de la première à la dernière.",
        "Remets les éléments dans l'ordre en touchant les étiquettes.",
    ),
    ActivityCode.TIMELINE: (
        "Touche d'abord ce qui s'est passé en premier.",
        "Place les événements du plus ancien au plus récent.",
        "Classe les événements dans l'ordre chronologique.",
    ),
    ActivityCode.CLASSIFY: (
        "Touche un mot, puis touche sa case.",
        "Touche une étiquette, puis la case où elle va.",
        "Range chaque élément dans la bonne catégorie.",
    ),
    ActivityCode.MEMORY: (
        "Retourne deux cartes. Trouve celles qui vont ensemble.",
        "Retourne les cartes deux par deux pour retrouver les paires.",
        "Retrouve les paires en retournant le moins de cartes possible.",
    ),
    ActivityCode.MAP: (
        "Lis le nom demandé. Touche sa place sur le dessin.",
        "Touche sur le dessin l'endroit de chaque nom demandé.",
        "Situe chaque élément demandé sur le document.",
    ),
    ActivityCode.WORD_FLASH: (
        "Regarde bien le mot. Il va se cacher. Écris-le.",
        "Mémorise le mot affiché, puis écris-le sans le voir.",
        "Mémorise l'orthographe du mot, puis écris-le de mémoire.",
    ),
    ActivityCode.DICTATION: (
        "Écoute bien le mot. Écris-le.",
        "Écoute le mot (touche le haut-parleur pour le réentendre), puis écris-le.",
        "Écris le mot dicté ; tu peux le réécouter autant que nécessaire.",
    ),
    ActivityCode.SENTENCE_DICTATION: (
        "Écoute bien la phrase. Écris-la.",
        "Écoute la phrase, puis écris-la. Tu peux la réécouter morceau par morceau.",
        "Écris la phrase dictée, ponctuation comprise ; réécoute-la si besoin.",
    ),
    ActivityCode.SCRAMBLE: (
        "Touche les lettres dans l'ordre. Tu écris le mot.",
        "Touche les lettres dans le bon ordre pour écrire le mot.",
        "Reconstitue le mot en touchant ses lettres dans l'ordre.",
    ),
    ActivityCode.UNJUMBLE: (
        "Touche les mots dans l'ordre. Tu écris la phrase.",
        "Touche les mots dans le bon ordre pour reformer la phrase de la leçon.",
        "Reconstitue la phrase de la leçon en remettant ses mots dans l'ordre.",
    ),
    ActivityCode.FIND_MATCH: (
        "Lis la phrase. Touche le mot qui va avec.",
        "Lis l'indice, puis touche la réponse qui lui correspond.",
        "Associe chaque indice à la réponse qui lui correspond.",
    ),
    ActivityCode.WHEEL: (
        "Touche la roue pour la faire tourner. Puis réponds.",
        "Fais tourner la roue : elle choisit ta question. Réponds, puis relance.",
        "Lance la roue, puis réponds à la question qu'elle désigne.",
    ),
    ActivityCode.BOX: (
        "Touche une boîte pour l'ouvrir. Réponds à la question.",
        "Ouvre les boîtes une par une et réponds à la question cachée dans chacune.",
        "Ouvre chaque boîte et réponds à la question qu'elle contient.",
    ),
    ActivityCode.RANDOM_CARDS: (
        "Tire une carte. Tu sais ? Retourne-la pour voir.",
        "Tire une carte, essaie de te souvenir, puis retourne-la pour vérifier.",
        "Tire une carte, récite la réponse, retourne-la et sois honnête.",
    ),
    ActivityCode.PICTURE_MATCH: (
        "Regarde l'image. Touche-la, puis touche son mot.",
        "Touche une image, puis le mot de la leçon qu'elle montre.",
        "Associe chaque image au terme de la leçon qu'elle illustre.",
    ),
    ActivityCode.PICTURE_FIND: (
        "Lis la phrase. Touche la bonne image.",
        "Lis la phrase à retenir, puis touche l'image qui la montre.",
        "Lis chaque énoncé et désigne l'image qui l'illustre.",
    ),
    ActivityCode.ALIGN: (
        "Regarde les points. Touche ceux qui sont sur une même ligne droite.",
        "Regarde la figure : touche les points alignés, ou réponds oui ou non.",
        "Observe la figure et repère les points alignés.",
    ),
    ActivityCode.NUMBER_LINE: (
        "Regarde la droite. Touche la bonne graduation.",
        "Compte les graduations : touche celle du nombre demandé, ou lis le nombre de la flèche.",
        "Repère le pas de la graduation, puis place ou lis le nombre.",
    ),
    ActivityCode.FRACTION_BAR: (
        "Touche les parts pour les colorier.",
        "Colorie le bon nombre de parts, ou dis quelle fraction est coloriée.",
        "Colorie la fraction demandée, ou retrouve la fraction coloriée.",
    ),
    ActivityCode.COLUMN_OP: (
        "Calcule en colonnes. Écris le résultat chiffre par chiffre.",
        "Pose l'opération : commence par les unités, n'oublie pas les retenues.",
        "Effectue l'opération posée, en commençant par la droite.",
    ),
    ActivityCode.WORD_HUNT: (
        "Touche tous les bons mots. Puis valide.",
        "Trouve et touche tous les éléments demandés, puis valide.",
        "Repère tous les éléments de la catégorie demandée.",
    ),
    ActivityCode.CONJUGATION: (
        "Touche une forme du verbe pour chaque ligne.",
        "Complète le tableau : une forme du verbe pour chaque personne.",
        "Conjugue le verbe à toutes les personnes demandées.",
    ),
    ActivityCode.PRONOUN: (
        "Touche le bon pronom pour chaque ligne.",
        "Trouve le pronom qui va avec chaque forme du verbe.",
        "Associe chaque forme conjuguée à son pronom personnel.",
    ),
    ActivityCode.SYNONYMS: (
        "Relie les mots qui veulent dire la même chose.",
        "Relie chaque mot à son synonyme : le mot qui a le même sens.",
        "Associe chaque mot à son synonyme.",
    ),
    ActivityCode.WORD_FAMILY: (
        "Touche le mot de la même famille.",
        "Trouve le mot qui a la même partie commune et la même idée.",
        "Choisis le mot de la même famille : même radical, même idée.",
    ),
    ActivityCode.SOUNDS: (
        "Touche 🔊 pour écouter le mot. Choisis le son qui manque.",
        "Écoute le mot avec 🔊, puis choisis les lettres qui manquent.",
        "Écoute le mot, puis choisis la graphie du son qui manque.",
    ),
    ActivityCode.ENGLISH_WORDS: (
        "Regarde ou écoute avec 🔊. Touche la bonne réponse.",
        "Regarde l'image ou écoute le mot avec 🔊, puis choisis la bonne réponse.",
        "Associe chaque image, mot entendu ou mot français à sa réponse.",
    ),
    ActivityCode.HOMOPHONE: (
        "Lis la phrase. Touche le bon mot.",
        "Lis chaque phrase et choisis le mot qui convient.",
        "Choisis l'homophone qui convient dans chaque phrase.",
    ),
    ActivityCode.ALPHA_ORDER: (
        "Touche les mots dans l'ordre de l'alphabet.",
        "Range les mots comme dans le dictionnaire : regarde la première lettre, puis la suivante.",
        "Range les mots dans l'ordre alphabétique.",
    ),
    ActivityCode.CLOCK: (
        "Regarde l'horloge. Touche la bonne heure.",
        "La petite aiguille montre les heures, la grande les minutes : quelle heure est-il ?",
        "Lis l'heure indiquée par l'horloge.",
    ),
    ActivityCode.MONEY: (
        "Compte l'argent. Touche la bonne réponse.",
        "Compte les pièces et les billets, ou touche ceux qu'il faut pour payer juste.",
        "Compte la somme, ou paie le prix exact.",
    ),
    ActivityCode.RULER: (
        "Regarde la règle. Combien mesure le trait rouge ?",
        "Lis où commence et où finit le segment sur la règle, puis choisis sa longueur.",
        "Mesure le segment avec la règle graduée.",
    ),
    ActivityCode.SYMMETRY: (
        "Touche les cases pour finir le dessin. Comme dans un miroir !",
        "Complète la figure de l'autre côté de l'axe : chaque case à la même distance.",
        "Construis le symétrique de la figure par rapport à l'axe.",
    ),
    ActivityCode.SYLLABLES: (
        "Touche entre deux lettres pour couper le mot.",
        "Coupe chaque mot en syllabes : touche entre les lettres là où tu entends une coupure.",
        "Découpe chaque mot en syllabes.",
    ),
    ActivityCode.COLORING: (
        "Choisis une couleur. Puis touche le dessin.",
        "Choisis une couleur de la légende, puis touche les zones à colorier.",
        "Colorie chaque zone selon la légende.",
    ),
}

_WRITING: dict[int, str] = {
    2: (
        "Élève de cycle 2 (CP à CE2), qui apprend à lire : phrases de 12 mots au plus, "
        "mots simples et concrets, une seule idée par phrase, pas de négation dans les "
        "questions, pas de mot savant sans l'expliquer. Chaque consigne commence par un verbe "
        "(Touche, Range, Écris, Choisis) et dit ce qu'il faut faire, comme à un enfant de 6 ans."
    ),
    3: (
        "Élève de cycle 3 (CM1 à 6e) : phrases de 20 mots au plus, vocabulaire de la leçon, "
        "une seule question à la fois, pas de double négation. Chaque consigne commence par "
        "un verbe et dit ce qu'il faut faire et selon quel critère."
    ),
    4: (
        "Élève de cycle 4 (5e à 3e) : phrases claires et précises, vocabulaire disciplinaire "
        "de la leçon, pas de tournure ambiguë."
    ),
}


def cycle(grade: str | None) -> int:
    """Cycle de la classe ; cycle 3 si la classe est inconnue."""
    try:
        return CYCLES[Grade(grade)] if grade else 3
    except ValueError:
        return 3


def instruction(code: str, grade: str | None) -> str | None:
    """Comment jouer, dit au niveau de l'enfant ; None pour un jeu inconnu."""
    try:
        texts = _TEXTS[ActivityCode(code)]
    except (ValueError, KeyError):
        return None
    return texts[cycle(grade) - 2]


def writing_rules(grade: str | None) -> str:
    return _WRITING[cycle(grade)]
