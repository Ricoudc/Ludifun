"""Accès à l'IA.

`AnthropicLLM` appelle Claude (vision + sorties structurées). `FakeLLM` est un
moteur déterministe hors-ligne : il permet de développer l'application mobile
et de lancer les tests sans clé API.
"""

import base64
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol

from app.ai import prompts
from app.ai.schemas import (
    AnalyzedNotion,
    GeneratedQuestion,
    LessonAnalysis,
    OpenAnswerEvaluation,
    QuestionBank,
)
from app.config import Settings


@dataclass
class LessonImage:
    data: bytes
    media_type: str  # image/jpeg, image/png, image/webp


class LLMError(RuntimeError):
    pass


class LLM(Protocol):
    def analyze_lesson(self, images: list[LessonImage], text: str | None) -> LessonAnalysis: ...

    def generate_questions(self, analysis: LessonAnalysis, per_notion: int) -> list[GeneratedQuestion]: ...

    def evaluate_open_answer(
        self, question: str, model_answer: str, given: str, grade: str
    ) -> OpenAnswerEvaluation: ...


class AnthropicLLM:
    def __init__(self, model: str):
        import anthropic

        self._client = anthropic.Anthropic()
        self._model = model

    def _parse(self, system: str, content: list[dict], output_format, effort: str):
        response = self._client.beta.messages.parse(
            model=self._model,
            max_tokens=16000,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": content}],
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            output_format=output_format,
            # Si le modèle principal décline, l'API relance la requête sur un modèle de repli.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise LLMError("La leçon n'a pas pu être traitée.")
        if response.stop_reason == "max_tokens" or response.parsed_output is None:
            raise LLMError("Réponse de l'IA incomplète.")
        return response.parsed_output

    def analyze_lesson(self, images: list[LessonImage], text: str | None) -> LessonAnalysis:
        content: list[dict] = []
        for i, image in enumerate(images, start=1):
            content.append({"type": "text", "text": f"Page {i} :"})
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image.media_type,
                        "data": base64.standard_b64encode(image.data).decode("ascii"),
                    },
                }
            )
        if text:
            content.append({"type": "text", "text": f"<lecon>\n{text}\n</lecon>"})
        content.append({"type": "text", "text": "Analyse cette leçon."})
        return self._parse(prompts.ANALYSIS_SYSTEM, content, LessonAnalysis, effort="high")

    def generate_questions(self, analysis: LessonAnalysis, per_notion: int) -> list[GeneratedQuestion]:
        payload = {
            "matiere": analysis.subject,
            "niveau": analysis.grade,
            "theme": analysis.title,
            "notions": [
                {"index": i, **n.model_dump()} for i, n in enumerate(analysis.notions)
            ],
        }
        content = [
            {
                "type": "text",
                "text": (
                    f"<lecon>\n{analysis.source_text}\n</lecon>\n"
                    f"<notions>\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n</notions>\n"
                    f"Génère {per_notion} questions par notion, de difficultés variées."
                ),
            }
        ]
        bank: QuestionBank = self._parse(prompts.GENERATION_SYSTEM, content, QuestionBank, effort="medium")
        return bank.questions

    def evaluate_open_answer(
        self, question: str, model_answer: str, given: str, grade: str
    ) -> OpenAnswerEvaluation:
        content = [
            {
                "type": "text",
                "text": (
                    f"Niveau : {grade}\n<question>{question}</question>\n"
                    f"<reponse_modele>{model_answer}</reponse_modele>\n"
                    f"<reponse_enfant>{given}</reponse_enfant>"
                ),
            }
        ]
        return self._parse(prompts.EVALUATION_SYSTEM, content, OpenAnswerEvaluation, effort="low")


# --------------------------------------------------------------------------- #
# Moteur hors-ligne
# --------------------------------------------------------------------------- #

DEMO_LESSON = (
    "La Révolution française commence en 1789. Le roi Louis XVI réunit les États généraux "
    "le 5 mai 1789 pour résoudre la crise financière. Le 14 juillet 1789, le peuple de Paris "
    "prend la Bastille, une prison symbole du pouvoir du roi. Le 26 août 1789, l'Assemblée "
    "adopte la Déclaration des droits de l'homme et du citoyen."
)

_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_WORD = re.compile(r"[a-zà-öø-ÿ0-9]+", re.IGNORECASE)
_STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "en", "est", "a", "au", "aux",
    "pour", "par", "que", "qui", "dans", "sur", "une", "son", "sa", "ses", "il", "elle",
    "ce", "cette", "l", "d", "se", "ne", "pas", "plus",
}


def _fold(word: str) -> str:
    word = unicodedata.normalize("NFKD", word.lower())
    return "".join(c for c in word if not unicodedata.combining(c))


def _keywords(text: str) -> set[str]:
    return {_fold(w) for w in _WORD.findall(text) if len(w) > 2 and w.lower() not in _STOPWORDS}


class FakeLLM:
    """Analyse et génération par règles simples, sans appel réseau."""

    def analyze_lesson(self, images: list[LessonImage], text: str | None) -> LessonAnalysis:
        source = (text or "").strip() or DEMO_LESSON
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", source) if len(s.strip()) > 10]
        notions: list[AnalyzedNotion] = []
        seen: set[str] = set()
        for sentence in sentences:
            years = [y for y in _YEAR.findall(sentence) if y not in seen]
            if years:
                seen.add(years[0])
                notions.append(
                    AnalyzedNotion(label=years[0], kind="date", content=sentence, importance="essentielle")
                )
            else:
                words = [w for w in _WORD.findall(sentence) if w.lower() not in _STOPWORDS]
                label = max(words, key=len) if words else sentence[:20]
                notions.append(
                    AnalyzedNotion(label=label, kind="concept", content=sentence, importance="importante")
                )
        title = sentences[0][:60] if sentences else "Leçon"
        return LessonAnalysis(
            readable=bool(notions),
            subject="Histoire" if _YEAR.search(source) else "Français",
            grade="CM1",
            title=title,
            summary=" ".join(sentences[:2]),
            source_text=source,
            notions=notions[:12],
        )

    def generate_questions(self, analysis: LessonAnalysis, per_notion: int) -> list[GeneratedQuestion]:
        labels = [n.label for n in analysis.notions]
        questions: list[GeneratedQuestion] = []
        for i, notion in enumerate(analysis.notions):
            distractors = [label for label in labels if label != notion.label][:3]
            while len(distractors) < 3:
                distractors.append(f"Aucune de ces réponses ({len(distractors) + 1})")
            choices = sorted([notion.label, *distractors])
            blanked = notion.content.replace(notion.label, "___", 1)
            candidates = [
                GeneratedQuestion(
                    notion_index=i, kind="qcm", difficulty=1,
                    prompt=f"Complète : {blanked}" if "___" in blanked else f"Quelle notion correspond à : « {notion.content} » ?",
                    choices=choices, answer=notion.label,
                    explanation=notion.content, pairs=[],
                ),
                GeneratedQuestion(
                    notion_index=i, kind="vrai_faux", difficulty=1,
                    prompt=notion.content, choices=["Vrai", "Faux"], answer="Vrai",
                    explanation=notion.content, pairs=[],
                ),
                GeneratedQuestion(
                    notion_index=i, kind="flashcard", difficulty=2,
                    prompt=f"Que dois-tu retenir sur « {notion.label} » ?", choices=[],
                    answer=notion.content, explanation=notion.content, pairs=[],
                ),
                GeneratedQuestion(
                    notion_index=i, kind="texte_a_trous" if "___" in blanked else "question_ouverte",
                    difficulty=2 if "___" in blanked else 4,
                    prompt=blanked if "___" in blanked else f"Explique avec tes mots : {notion.label}.",
                    choices=[], answer=notion.label if "___" in blanked else notion.content,
                    explanation=notion.content, pairs=[],
                ),
            ]
            questions.extend(candidates[:per_notion])
        return questions

    def evaluate_open_answer(
        self, question: str, model_answer: str, given: str, grade: str
    ) -> OpenAnswerEvaluation:
        expected = _keywords(model_answer)
        found = expected & _keywords(given)
        score = len(found) / len(expected) if expected else 0.0
        missing = sorted(expected - found)[:5]
        feedback = (
            "Bravo, ta réponse contient l'essentiel !"
            if score >= 0.6
            else "C'est un bon début. Relis la leçon pour compléter ta réponse."
        )
        return OpenAnswerEvaluation(score=round(score, 2), feedback=feedback, missing_points=missing)


def build_llm(settings: Settings) -> LLM:
    if settings.llm_provider == "anthropic":
        return AnthropicLLM(settings.llm_model)
    return FakeLLM()
