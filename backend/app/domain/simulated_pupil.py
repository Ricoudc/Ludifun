"""Un « élève simulé » : répond juste aux notions qu'il connaît, faux aux autres.

Sert aux tests et à la famille de démonstration (`python -m app.tools.demo_family`).
"""

from collections.abc import Callable
from typing import Any

from app.domain.activities.base import ActivityCode, BuiltActivity

Knows = Callable[[str], bool]


def respond(activity: BuiltActivity, knows: Knows) -> dict[str, Any]:
    s = activity.solution
    single_ok = knows(activity.knowledge_ids[0])
    match activity.type:
        case ActivityCode.MCQ:
            wrong = next(c["id"] for c in activity.payload["choices"] if c["id"] != s["choice_id"])
            return {"choice_id": s["choice_id"] if single_ok else wrong}
        case ActivityCode.TRUE_FALSE:
            return {"value": s["value"] if single_ok else not s["value"]}
        case ActivityCode.FILL_BLANK:
            return {"text": s["answers"][0] if single_ok else "je ne sais pas"}
        case ActivityCode.FLASHCARD:
            return {"self_assessment": "knew" if single_ok else "didnt_know"}
        case ActivityCode.OPEN_QUESTION:
            return {"text": s["model_answer"] if single_ok else "je ne sais pas"}
        case ActivityCode.MATCH:
            known = [
                [left, right] for left, right in s["pairs"].items() if knows(s["knowledge_by_left"][left])
            ]
            return {"pairs": known}
        case ActivityCode.SPEED_CHALLENGE:
            answers = [
                {"id": sid, "value": value if knows(s["knowledge_by_statement"][sid]) else not value}
                for sid, value in s["answers"].items()
            ]
            return {"answers": answers, "elapsed_ms": 20000}
        case ActivityCode.ORDER:
            order = list(s["order"])
            return {"order": order if single_ok else order[1:] + order[:1]}  # tout décalé d'un cran
        case ActivityCode.CLASSIFY:
            names = list(s["names"])
            return {
                "assignments": [
                    [item, category if single_ok else names[(names.index(category) + 1) % len(names)]]
                    for item, category in s["categories"].items()
                ]
            }
        case ActivityCode.TIMELINE:
            order = list(s["order"])
            unknown = [i for i, item in enumerate(order) if not knows(s["knowledge_by_item"][item])]
            if len(unknown) == 1:  # une seule date inconnue : échangée avec sa voisine
                unknown.append(unknown[0] - 1 if unknown[0] else 1)
            moved = [order[i] for i in unknown]
            for position, item in zip(unknown, moved[1:] + moved[:1], strict=True):
                order[position] = item
            return {"order": order}
        case ActivityCode.MEMORY:
            by_knowledge: dict[str, list[str]] = {}
            for card, knowledge in s["knowledge_by_card"].items():
                by_knowledge.setdefault(knowledge, []).append(card)
            cards = list(s["knowledge_by_card"])
            moves: list[list[str]] = []
            for knowledge, (first, second) in by_knowledge.items():
                if not knows(knowledge):  # deux essais ratés avant de trouver
                    other = next(c for c in cards if s["knowledge_by_card"][c] != knowledge)
                    moves += [[first, other], [second, other]]
                moves.append([first, second])
            return {"moves": moves}
    raise ValueError(f"type d'activité inconnu : {activity.type}")
