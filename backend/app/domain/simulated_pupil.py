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
    raise ValueError(f"type d'activité inconnu : {activity.type}")
