import random

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlmodel import Session, func, select

from app.ai.client import LLM, LessonImage, LLMError
from app.config import get_settings
from app.db import get_session
from app.deps import get_llm
from app.models import Child, Lesson, Notion, NotionMastery, Question, RevisionSession
from app.schemas import LessonOut, NotionOut, QuestionOut, SessionCreate, SessionOut
from app.services import lessons as lesson_service
from app.services.planner import MODES, plan_session

router = APIRouter(prefix="/lessons", tags=["leçons"])

ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def get_lesson_or_404(lesson_id: int, db: Session) -> Lesson:
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Leçon introuvable.")
    return lesson


def lesson_out(db: Session, lesson: Lesson) -> LessonOut:
    notions = db.exec(select(Notion).where(Notion.lesson_id == lesson.id)).all()
    count = db.exec(select(func.count()).select_from(Question).where(Question.lesson_id == lesson.id)).one()
    return LessonOut(
        **lesson.model_dump(include={"id", "child_id", "subject", "grade", "title", "summary", "created_at"}),
        notions=[NotionOut(**n.model_dump()) for n in notions],
        question_count=count,
    )


@router.post("", response_model=LessonOut, status_code=status.HTTP_201_CREATED)
async def create_lesson(
    child_id: int = Form(...),
    text: str | None = Form(default=None, max_length=20000),
    images: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_session),
    llm: LLM = Depends(get_llm),
) -> LessonOut:
    """Crée une leçon à partir de photos (et/ou d'un texte saisi).

    Les photos sont lues en mémoire, envoyées à l'IA puis oubliées :
    elles ne sont jamais enregistrées sur le serveur.
    """
    settings = get_settings()
    child = db.get(Child, child_id)
    if child is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enfant introuvable.")
    if not images and not (text and text.strip()):
        raise HTTPException(422, "Ajoute une photo ou un texte.")
    if len(images) > settings.max_images_per_lesson:
        raise HTTPException(
            422,
            f"{settings.max_images_per_lesson} pages maximum par leçon.",
        )

    lesson_images: list[LessonImage] = []
    for upload in images:
        if upload.content_type not in ALLOWED_MEDIA_TYPES:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Format d'image non supporté.")
        data = await upload.read()
        if len(data) > settings.max_image_bytes:
            raise HTTPException(413, "Photo trop lourde.")
        lesson_images.append(LessonImage(data=data, media_type=upload.content_type))

    try:
        lesson = lesson_service.create_lesson(
            db, llm, child, lesson_images, text, settings.questions_per_notion
        )
    except lesson_service.UnreadableLesson as exc:
        raise HTTPException(422, str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return lesson_out(db, lesson)


@router.get("/{lesson_id}", response_model=LessonOut)
def read_lesson(lesson_id: int, db: Session = Depends(get_session)) -> LessonOut:
    return lesson_out(db, get_lesson_or_404(lesson_id, db))


@router.delete("/{lesson_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lesson(lesson_id: int, db: Session = Depends(get_session)) -> None:
    lesson_service.delete_lesson(db, get_lesson_or_404(lesson_id, db))


@router.post("/{lesson_id}/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def start_session(lesson_id: int, body: SessionCreate, db: Session = Depends(get_session)) -> SessionOut:
    lesson = get_lesson_or_404(lesson_id, db)
    notions = db.exec(select(Notion).where(Notion.lesson_id == lesson.id)).all()
    questions = db.exec(select(Question).where(Question.lesson_id == lesson.id)).all()
    masteries = db.exec(
        select(NotionMastery).where(
            NotionMastery.child_id == lesson.child_id,
            NotionMastery.notion_id.in_([n.id for n in notions]),
        )
    ).all()
    levels = {m.notion_id: m.level for m in masteries}

    rng = random.Random()
    selected = plan_session(body.mode, list(notions), list(questions), levels, rng)
    if not selected:
        raise HTTPException(422, "Aucune question disponible pour ce mode.")

    session = RevisionSession(
        child_id=lesson.child_id,
        lesson_id=lesson.id,
        mode=body.mode,
        question_ids=[q.id for q in selected],
        time_limit_s=MODES[body.mode].time_limit_s,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return SessionOut(
        id=session.id,
        lesson_id=lesson.id,
        mode=session.mode,
        time_limit_s=session.time_limit_s,
        questions=[QuestionOut.from_question(q, rng) for q in selected],
    )
