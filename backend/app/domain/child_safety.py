"""Contrôle du contenu destiné à l'enfant (cahier des charges §141).

Tout texte que l'IA écrit pour l'enfant (exercices, aides, retours sur une réponse rédigée,
guidage des devoirs, réponses et questions tirées des sites) passe par `concern` avant d'être
gardé. Sont refusés : le langage grossier, insultant ou blessant, les demandes d'informations
personnelles ou de contact, les adresses de sites, courriels et numéros de téléphone, les
informations dangereuses, la violence crue, le contenu pour adultes, la manipulation (« c'est
notre secret »).

Un passage signalé est accepté s'il figure déjà dans le texte d'origine (la leçon, l'énoncé,
l'extrait cité) : une leçon d'histoire parle de torture, une leçon d'EMC des réseaux sociaux,
une leçon de grammaire de « Où habites-tu ? ». Ce que l'IA ajoute d'elle-même est écarté.
Déterministe, sans IA ni réseau ; une liste de mots ne voit pas tout, elle s'ajoute aux
consignes des prompts et aux citations vérifiées.
"""

import re
from collections.abc import Iterable, Iterator
from enum import StrEnum
from typing import Any

from app.domain.text import normalize


class Concern(StrEnum):
    LANGUAGE = "langage inadapté à un enfant"
    PERSONAL_DATA = "demande d'informations personnelles"
    CONTACT = "coordonnées ou demande de contact"
    DANGER = "information dangereuse"
    VIOLENCE = "violence inutile"
    ADULT = "contenu pour adultes"
    MANIPULATION = "manipulation"


def _words(*alternatives: str) -> tuple[re.Pattern[str], ...]:
    """Des mots ou expressions entiers, écrits comme `normalize` les rend (minuscules, sans
    accents, ponctuation remplacée par une espace). Un motif par famille de mots : la leçon qui
    parle de « torture » excuse « torturaient », pas « merde »."""
    return tuple(re.compile(r"(?<!\w)(?:" + a + r")(?!\w)") for a in alternatives)


# Sur le texte tel quel : la ponctuation compte.
_RAW: tuple[tuple[Concern, re.Pattern[str]], ...] = (
    (Concern.CONTACT, re.compile(r"https?://\S+|\bwww\.\S+", re.IGNORECASE)),
    (Concern.CONTACT, re.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", re.IGNORECASE)),
    (Concern.CONTACT, re.compile(r"(?<![\d,.])(?:\+33\s?|0)[1-9](?:[ .-]?\d{2}){4}(?![\d,.])")),
)

# Sur le texte normalisé.
_NORMALIZED: tuple[tuple[Concern, tuple[re.Pattern[str], ...]], ...] = (
    (
        Concern.LANGUAGE,
        _words(
            r"merde\w*",
            r"putains?",
            r"putes?",
            r"salopes?",
            r"salauds?",
            r"connards?",
            r"connasses?",
            r"cons?",
            r"conne",
            r"encul\w*",
            r"niqu\w*",
            "ntm",
            "fdp",
            r"(?:ferme )?ta gueule",
            r"bites?",
            r"couilles?",
            "chier",
            r"chiants?",
            r"chiantes?",
            "foutre",
            "bordel",
            r"branl\w*",
            r"batards?",
            r"petasses?",
            "pd",
            r"pedes?",
            r"gouines?",
            r"negres?",
            r"bougnoules?",
            r"youpins?",
            r"abruti(?:e|s|es)?",
            r"debiles?",
            r"cretin(?:e|s|es)?",
            r"imbeciles?",
            r"idiot(?:e|s|es)?",
            r"stupides?",
            r"(?:tu es|t es|tu n es qu un|tu n es qu une) (?:nul|nulle|bete|nase|naze|un boulet)",
        ),
    ),
    (
        Concern.PERSONAL_DATA,
        _words(
            r"(?:ton|ta|votre) (?:adresse(?: mail| e mail)?|e ?mail|mail)",
            r"(?:ton|votre) (?:numero de (?:telephone|portable)|telephone|portable)",
            r"(?:ton|votre) nom de famille",
            r"(?:ton|votre) (?:mot de passe|code secret)",
            r"(?:ta|votre) date de naissance",
            r"(?:ta|votre) carte bancaire",
            r"ou (?:est ce que tu habites|tu habites|habites tu|vis tu|tu vis)",
            r"dans quelle (?:ville|rue) (?:habites tu|tu habites|vis tu)",
            r"(?:le nom|l adresse) de (?:ton ecole|ton college|ta ville|tes parents|ta maman|"
            r"ton papa|ta mere|ton pere)",
            r"(?:une )?photo de (?:toi|ta famille|ta maison|ta chambre|ton visage)",
            r"selfies?",
        ),
    ),
    (
        Concern.CONTACT,
        _words(
            r"(?:contacte|contactez|appelle|appelez|ajoute|ajoutez|rejoins|rejoignez) moi",
            # « Écris-moi une phrase » est une consigne ; « écris-moi sur… » une prise de contact.
            r"(?:ecris|ecrivez|envoie|envoyez) moi (?:sur|a|au|par|un message|un mail|une photo)",
            r"snapchat",
            r"snap",
            r"instagram",
            r"insta",
            r"tiktok",
            r"whatsapp",
            r"discord",
            r"facebook",
            r"messenger",
            r"telegram",
            r"twitter",
            r"youtube",
        ),
    ),
    (
        Concern.DANGER,
        _words(
            r"suicid\w*",
            r"(?:te|se) tuer",
            r"tue toi",
            r"(?:te|se) pendre",
            r"pends toi",
            r"scarifi\w*",
            r"automutil\w*",
            r"fais toi (?:du )?mal",
            r"bombes? artisanales?",
            r"fabriquer une bombe",
            r"drogues?",
            r"cocaine",
            r"cannabis",
            r"hasch\w*",
            r"ecstasy",
            r"avale (?:des |les |un |une )?(?:medicaments?|pilules?|cachets?)",
            r"melange (?:l |de l )?eau de javel",
            r"joue avec (?:des |les )?allumettes",
        ),
    ),
    (
        Concern.VIOLENCE,
        _words(
            r"egorg\w*",
            r"eventr\w*",
            r"demembr\w*",
            r"tortur\w*",
            r"viols?",
            r"sanguinolent\w*",
            "gore",
            r"(?:bain|mare) de sang",
        ),
    ),
    (
        Concern.ADULT,
        _words(
            r"porno\w*",
            r"erotiques?",
            "sexy",
            r"sexuel\w*",
            "faire l amour",
            r"nudes?",
        ),
    ),
    (
        Concern.MANIPULATION,
        _words(
            r"c est notre (?:petit )?secret",
            r"notre petit secret",
            r"ne (?:le |la |les )?(?:dis|repete|raconte) (?:pas|rien) a tes parents",
            r"ne (?:le |la |les )?(?:dis|repete|raconte) a personne",
            r"n en parle a personne",
            r"sans le dire a tes parents",
            r"personne ne doit (?:le )?savoir",
            r"cache le a tes parents",
        ),
    ),
)


def concern(text: str, context: str = "") -> Concern | None:
    """Ce qui pose problème dans `text` pour un enfant, ou None. Un passage déjà présent dans
    `context` (le texte d'origine) est accepté."""
    if not text.strip():
        return None
    around = f" {normalize(context)} "
    for kind, pattern in _RAW:
        # Une adresse, un numéro : seulement s'ils sont recopiés de la leçon.
        if any(f" {normalize(m.group(0))} " not in around for m in pattern.finditer(text)):
            return kind
    flat = normalize(text)
    for kind, patterns in _NORMALIZED:
        if any(p.search(flat) and not p.search(around) for p in patterns):
            return kind
    return None


def strings(value: Any) -> Iterator[str]:
    """Tous les textes d'une sortie de l'IA (listes et objets imbriqués)."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from strings(v)
    elif isinstance(value, list | tuple):
        for v in value:
            yield from strings(v)


def unsafe_reason(texts: Any, context: str | Iterable[str] = "") -> str | None:
    """La raison de refuser `texts` (un texte, ou une structure qui en contient) pour un enfant ;
    None si rien ne pose problème."""
    joined = context if isinstance(context, str) else "\n".join(context)
    for text in strings(texts):
        if (found := concern(text, joined)) is not None:
            return f"contenu refusé pour un enfant : {found.value}"
    return None
