import json

from app.models import NotionMastery
from app.db import engine
from sqlmodel import Session, select


def answer_everything(client, session, correct: bool):
    """Répond à toutes les questions d'une séance, juste ou faux."""
    from app.models import Question

    with Session(engine) as db:
        truth = {q.id: q for q in db.exec(select(Question)).all()}
    results = []
    for q in session["questions"]:
        expected = truth[q["id"]]
        if q["kind"] == "flashcard":
            given = "je savais" if correct else "je ne savais pas"
        elif q["kind"] == "association":
            given = json.dumps({p["left"]: p["right"] for p in expected.pairs} if correct else {})
        else:
            given = expected.answer if correct else "zzz"
        r = client.post(f"/sessions/{session['id']}/answers", json={"question_id": q["id"], "answer": given})
        assert r.status_code == 200, r.text
        results.append(r.json())
    return results


def test_lesson_from_photo_is_analyzed(lesson):
    assert lesson["subject"] == "Histoire"
    labels = [n["label"] for n in lesson["notions"]]
    assert "1789" in labels
    assert lesson["question_count"] > 0


def test_lesson_from_text(client, child):
    text = "Le verbe être au présent : je suis, tu es, il est. Nous sommes, vous êtes, ils sont."
    r = client.post("/lessons", data={"child_id": child["id"], "text": text})
    assert r.status_code == 201
    assert r.json()["notions"]


def test_lesson_requires_content(client, child):
    r = client.post("/lessons", data={"child_id": child["id"]})
    assert r.status_code == 422


def test_rejects_non_image_upload(client, child):
    r = client.post("/lessons", data={"child_id": child["id"]}, files=[("images", ("a.pdf", b"x", "application/pdf"))])
    assert r.status_code == 415


def test_session_hides_answers(client, lesson):
    r = client.post(f"/lessons/{lesson['id']}/sessions", json={"mode": "quiz_rapide"})
    assert r.status_code == 201
    session = r.json()
    assert 0 < len(session["questions"]) <= 10
    for q in session["questions"]:
        assert q["kind"] in ("qcm", "vrai_faux")
        assert "answer" not in q


def test_defi_has_time_limit(client, lesson):
    session = client.post(f"/lessons/{lesson['id']}/sessions", json={"mode": "defi"}).json()
    assert session["time_limit_s"] == 60


def test_full_loop_success_raises_mastery(client, lesson, child):
    session = client.post(f"/lessons/{lesson['id']}/sessions", json={"mode": "entrainement"}).json()
    results = answer_everything(client, session, correct=True)
    assert all(r["correct"] for r in results)

    report = client.post(f"/sessions/{session['id']}/finish").json()
    assert report["score_on_10"] == 10
    assert all(n["status"] == "acquis" for n in report["notions"])
    assert all(n["level"] == 3 for n in report["notions"])
    assert all(n["next_review_at"] for n in report["notions"])

    progress = client.get(f"/children/{child['id']}/progress").json()
    assert progress["success_rate"] == 1.0
    assert progress["subjects"][0]["subject"] == "Histoire"


def test_full_loop_failure_marks_notions_to_review(client, lesson, child):
    session = client.post(f"/lessons/{lesson['id']}/sessions", json={"mode": "quiz_rapide"}).json()
    answer_everything(client, session, correct=False)
    report = client.post(f"/sessions/{session['id']}/finish").json()
    assert report["score_on_10"] == 0
    assert all(n["status"] == "a_revoir" for n in report["notions"])

    progress = client.get(f"/children/{child['id']}/progress").json()
    assert len(progress["to_strengthen"]) == len(report["notions"])


def test_answer_twice_is_rejected(client, lesson):
    session = client.post(f"/lessons/{lesson['id']}/sessions", json={"mode": "quiz_rapide"}).json()
    body = {"question_id": session["questions"][0]["id"], "answer": "x"}
    assert client.post(f"/sessions/{session['id']}/answers", json=body).status_code == 200
    assert client.post(f"/sessions/{session['id']}/answers", json=body).status_code == 409


def test_finished_session_is_closed(client, lesson):
    session = client.post(f"/lessons/{lesson['id']}/sessions", json={"mode": "quiz_rapide"}).json()
    client.post(f"/sessions/{session['id']}/finish")
    body = {"question_id": session["questions"][0]["id"], "answer": "x"}
    assert client.post(f"/sessions/{session['id']}/answers", json=body).status_code == 409


def test_delete_child_erases_everything(client, lesson, child):
    session = client.post(f"/lessons/{lesson['id']}/sessions", json={"mode": "quiz_rapide"}).json()
    answer_everything(client, session, correct=True)
    client.post(f"/sessions/{session['id']}/finish")

    assert client.delete(f"/children/{child['id']}").status_code == 204
    assert client.get(f"/lessons/{lesson['id']}").status_code == 404
    with Session(engine) as db:
        assert db.exec(select(NotionMastery)).all() == []
