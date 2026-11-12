"""« En bref » : les 7 derniers jours de l'enfant en quelques phrases, pour le parent."""

from app.domain.weekly_summary import RecentFacts, weekly_summary


def test_an_active_week_says_what_counts_and_what_to_do() -> None:
    lines = weekly_summary(
        RecentFacts(
            days_active=4,
            sessions=6,
            minutes=52,
            previous_minutes=40,
            mastered=["Numérateur", "Dénominateur", "Fraction d'un nombre", "Comparer"],
            weak=("Simplifier une fraction", "Les fractions"),
            recurring=("Confond avec une autre notion", "Numérateur"),
            help_questions=3,
            reviews_due=2,
        )
    )
    assert lines == [
        "📅 Révisé 4 jours sur 7 : 6 séances, 52 min (+12 min par rapport aux 7 jours d'avant).",
        "✅ Bien acquis : Numérateur, Dénominateur, Fraction d'un nombre et 1 autre.",
        "🟠 À renforcer : Simplifier une fraction (Les fractions).",
        "🔁 Erreur qui revient sur « Numérateur » : confond avec une autre notion.",
        "❓ Aide demandée sur 3 questions.",
        "👉 La mission du jour reprend 2 notions à revoir : quelques minutes suffisent.",
    ]


def test_a_quiet_week() -> None:
    lines = weekly_summary(RecentFacts(days_active=0, sessions=0, minutes=0, previous_minutes=30))
    assert lines == [
        "Aucune révision ces 7 derniers jours.",
        "👉 Une séance de 10 minutes suffit pour reprendre l'habitude.",
    ]


def test_small_changes_and_singulars() -> None:
    lines = weekly_summary(
        RecentFacts(days_active=1, sessions=1, minutes=12, previous_minutes=10, reports_to_see=1)
    )
    assert lines[0] == "📅 Révisé 1 jour sur 7 : 1 séance, 12 min."  # 2 min d'écart : rien
    assert lines[1] == "🚩 1 question signalée à regarder."
    assert lines[-1].startswith("👉 Regardez d'abord les questions signalées")


def test_everything_up_to_date() -> None:
    lines = weekly_summary(RecentFacts(days_active=3, sessions=3, minutes=30, previous_minutes=0))
    assert lines[-1] == "👉 Tout est à jour : une nouvelle leçon peut être ajoutée."
    assert "par rapport" not in lines[0]  # rien à comparer la première semaine
