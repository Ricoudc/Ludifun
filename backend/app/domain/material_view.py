"""Le matériel d'une notion, lisible par le parent (étape 25) : toutes les questions que l'enfant
pourra voir, avec leurs réponses, pour vérifier qu'elles sont claires et à son niveau.
"""

from dataclasses import dataclass

from app.domain.activities.base import ActivityCode
from app.domain.knowledge import KnowledgeMaterial


@dataclass(frozen=True)
class Block:
    title: str  # le jeu (« Questions à choix », « Vrai ou faux »…)
    lines: list[str]  # une ligne par question, réponse comprise
    game: ActivityCode | None = None  # le jeu qui s'en sert : sa consigne est montrée au parent


def material_blocks(material: KnowledgeMaterial) -> list[Block]:
    blocks: list[Block] = []

    def add(title: str, lines: list[str], game: ActivityCode | None = None) -> None:
        if lines:
            blocks.append(Block(title, lines, game))

    add(
        "❓ Questions à choix",
        [
            f"{q.stem}\n✅ {q.answer}   ✗ {' · '.join(q.distractors)}"
            for q in sorted(material.questions, key=lambda q: q.difficulty)
        ],
        ActivityCode.MCQ,
    )
    add(
        "✅ Vrai ou faux",
        [f"Vrai : {s}" for s in material.true_statements]
        + [f"Faux : {s}" for s in material.false_statements],
        ActivityCode.TRUE_FALSE,
    )
    if material.cloze:
        add(
            "✏️ Phrase à compléter",
            [f"{material.cloze.text}\n✅ {' / '.join(material.cloze.answers)}"],
            ActivityCode.FILL_BLANK,
        )
    if material.pair:
        add("🔗 À relier", [f"{material.pair.left} ↔ {material.pair.right}"], ActivityCode.MATCH)
    if material.flashcard:
        add(
            "🃏 Carte mémoire",
            [f"{material.flashcard.front}\n↪ {material.flashcard.back}"],
            ActivityCode.FLASHCARD,
        )
    if material.sorting:
        add(
            "🗂️ Jeu de tri",
            [material.sorting.prompt]
            + [f"{box.name} : {', '.join(box.members)}" for box in material.sorting.categories],
            ActivityCode.CLASSIFY,
        )
    if material.sequence:
        add(
            "🔢 Remettre dans l'ordre",
            [material.sequence.prompt, " → ".join(material.sequence.items)],
            ActivityCode.ORDER,
        )
    add(
        "💬 Questions à rédiger",
        [f"{q.prompt}\nRéponse attendue : {q.model_answer}" for q in material.open_questions],
        ActivityCode.OPEN_QUESTION,
    )
    help_lines = []
    if material.help:
        if material.help.hint:
            help_lines.append(f"Indice : {material.help.hint}")
        if material.help.reminder:
            help_lines.append(f"Rappel : {material.help.reminder}")
        if material.help.example:
            help_lines.append(f"Exemple : {material.help.example.question} → {material.help.example.answer}")
    if material.tip:
        help_lines.append(f"Astuce : {material.tip}")
    help_lines.append(f"Explication après une erreur : {material.explanation}")
    add("🆘 Aides", help_lines)
    return blocks
