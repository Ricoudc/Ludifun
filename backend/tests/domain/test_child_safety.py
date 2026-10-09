"""Contrôle du contenu destiné à l'enfant (§141) : ce que l'IA ajoute d'inadapté est écarté,
ce qui vient de la leçon est gardé."""

import copy
import json
from pathlib import Path

import pytest

from app.ai.schemas import EvaluationOutput
from app.domain.child_safety import Concern, concern, strings, unsafe_reason
from app.domain.homework import check_plan
from app.domain.sources import Excerpt, Quote, check_answer
from app.domain.validation import validate_analysis, validate_material
from app.services.answer_evaluation import to_evaluation
from tests.domain.conftest import ReferenceLesson
from tests.domain.test_homework import raw_plan


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Ajoute-moi sur Snapchat pour réviser !", Concern.CONTACT),
        ("Écris-moi sur WhatsApp.", Concern.CONTACT),
        ("Plus d'exercices sur www.jeux-gratuits.fr", Concern.CONTACT),
        ("Envoie ta réponse à prof@exemple.fr", Concern.CONTACT),
        ("Appelle le 06 12 34 56 78 pour la réponse.", Concern.CONTACT),
        ("Quelle est ton adresse ?", Concern.PERSONAL_DATA),
        ("Écris ton nom de famille et ta date de naissance.", Concern.PERSONAL_DATA),
        ("Dans quelle ville habites-tu ?", Concern.PERSONAL_DATA),
        ("Envoie une photo de toi.", Concern.PERSONAL_DATA),
        ("Quel est ton mot de passe ?", Concern.PERSONAL_DATA),
        ("Tu es nul, recommence.", Concern.LANGUAGE),
        ("Cette réponse est stupide.", Concern.LANGUAGE),
        ("Merde, c'est faux !", Concern.LANGUAGE),
        ("Les soldats ont égorgé les prisonniers.", Concern.VIOLENCE),
        ("Il y avait une mare de sang.", Concern.VIOLENCE),
        ("Mélange l'eau de javel avec du vinaigre.", Concern.DANGER),
        ("C'est notre secret : ne le dis pas à tes parents.", Concern.MANIPULATION),
        ("Un film érotique", Concern.ADULT),
    ],
)
def test_what_a_child_must_not_read(text: str, expected: Concern) -> None:
    assert concern(text) is expected


@pytest.mark.parametrize(
    "text",
    [
        "Écris-moi une phrase avec un verbe au futur.",
        "Calcule 0,12 + 3,45.",
        "Combien font 3 x 4 ?",
        "Le volcan est explosif.",
        "L'héroïne du roman est courageuse.",
        "Le 14 juillet 1789, le peuple prend la Bastille.",
        "Tu as presque trouvé : relis la deuxième phrase.",
        "Écris 1 234 567 890 en lettres.",
        "Écris ton prénom en lettres attachées.",
        "Le violon et la viole sont des instruments.",
    ],
)
def test_ordinary_school_sentences_pass(text: str) -> None:
    assert concern(text) is None


def test_what_the_lesson_says_is_kept() -> None:
    history = "Au Moyen Âge, la torture était utilisée pour faire avouer les accusés."
    assert concern("Les juges torturaient-ils les accusés ?", history) is None
    assert concern("Les juges torturaient-ils les accusés ?") is Concern.VIOLENCE
    # La même famille de mots, pas un autre mot de la liste.
    assert concern("Merde, la torture !", history) is Concern.LANGUAGE
    grammar = "Transforme en question : Tu habites à Lyon. → Où habites-tu ?"
    assert concern("Quelle question correspond à « Où habites-tu ? » ?", grammar) is None
    emc = "Sur Instagram ou TikTok, je ne donne jamais mon adresse."
    assert concern("Sur quels réseaux ne faut-il jamais donner son adresse ? Instagram", emc) is None
    # Une adresse de site n'est gardée que recopiée de la leçon.
    assert concern("Va sur www.vikidia.org", "Pour chercher : www.vikidia.org") is None
    assert concern("Va sur www.autre-site.com", "Pour chercher : www.vikidia.org") is Concern.CONTACT


def test_no_reference_lesson_is_flagged() -> None:
    for path in Path("reference_lessons").glob("*.json"):
        for text in strings(json.loads(path.read_text(encoding="utf-8"))):
            assert concern(text) is None, (path.name, text)


def test_unsafe_material_is_dropped_the_rest_kept(history: ReferenceLesson) -> None:
    item = history.analysis.item("k1")
    raw = copy.deepcopy(history.raw["material"]["k1"])
    raw["questions"][0]["stem"] = "Ajoute-moi sur Snapchat : en quelle année commence la Révolution ?"
    raw["tip"] = "Tu es nul en dates, retiens 1789."
    raw["explanation"] = "Écris ton adresse puis retiens que la Révolution commence en 1789."
    result = validate_material(item, raw, history.raw["ocr_text"])
    reasons = {r.element: r.reason for r in result.rejected}
    assert reasons["questions[0]"] == "contenu refusé pour un enfant : coordonnées ou demande de contact"
    assert reasons["tip"].endswith("langage inadapté à un enfant")
    assert "explanation" in reasons
    assert result.material.tip is None
    assert result.material.explanation == item.statement  # la phrase « à retenir »
    assert len(result.material.questions) == len(history.raw["material"]["k1"]["questions"]) - 1


def test_a_notion_with_unsafe_text_is_rejected(history: ReferenceLesson) -> None:
    raw = copy.deepcopy(history.raw["analysis"])
    raw["knowledge"][0]["statement"] = "La Révolution commence en 1789, c'est notre petit secret."
    validation = validate_analysis(raw, history.raw["ocr_text"])
    assert any("manipulation" in r.reason for r in validation.rejected)
    assert len(validation.analysis.knowledge) == len(raw["knowledge"]) - 1


def test_homework_guidance_is_screened() -> None:
    statement = "Paul a 24 billes. Il en donne 16 à Léa. Combien lui en reste-t-il ?"
    steps = [*raw_plan()["steps"], {"kind": "hint", "text": "Demande la réponse sur Discord."}]
    plan, rejected = check_plan(raw_plan(steps=steps, check="Tu es bête si tu ne trouves pas 8."), statement)
    assert plan is not None
    assert any("coordonnées ou demande de contact" in r for r in rejected)
    assert all("Discord" not in s.text for s in plan.steps)
    assert plan.check == "Relis la question : ta réponse y répond-elle ?"
    refused, why = check_plan(raw_plan(task="Donne ton adresse et on cherche les billes."), statement)
    assert refused is None and "informations personnelles" in why[0]


def test_sourced_answers_and_feedback_are_screened() -> None:
    text = "La Bastille était une prison royale."
    page = Excerpt(1, "https://fr.vikidia.org/wiki/Bastille", "Bastille", text)
    quote = [Quote(1, text)]
    assert check_answer("C'était une prison royale.", quote, [page], found=True) is not None
    assert check_answer("Une prison où l'on torturait.", quote, [page], found=True) is None

    def feedback(text: str) -> EvaluationOutput:
        return EvaluationOutput(
            score=0.5, key_points_found=[], missing=[], error_type=None, confidence=0.9, feedback=text
        )

    context = ["Pourquoi le peuple prend-il la Bastille ?", "C'est le symbole du roi."]
    assert to_evaluation(feedback("Bien vu ! Pense aussi au roi."), [], context) is not None
    assert to_evaluation(feedback("Réponse stupide, relis la leçon."), [], context) is None
    assert unsafe_reason({"a": ["ok", "Ajoute-moi sur Snapchat"]}) is not None
