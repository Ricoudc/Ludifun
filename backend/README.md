# Ludifun — backend

API FastAPI + PostgreSQL. Architecture et règles : [cahier des charges §13](../docs/cahier-des-charges-v1.md#13-architecture-fastapi).

## Prérequis

- [uv](https://docs.astral.sh/uv/) (gère Python 3.12 et les dépendances figées dans `uv.lock`)
- Docker (pour PostgreSQL)

## Démarrer

```bash
# Depuis la racine du dépôt : PostgreSQL (bases ludifun + ludifun_test)
docker compose up -d db

cd backend
uv sync                              # installe tout, dont les outils de dev
uv run alembic upgrade head          # crée / met à jour le schéma
uv run uvicorn app.main:app --reload # http://localhost:8000/docs
```

Ou toute la pile d'un coup : `docker compose up -d --build` (l'API applique les migrations au démarrage).

## Analyser une vraie leçon (sans l'application)

```bash
export ANTHROPIC_API_KEY=...            # ou `ant auth login`
uv run python -m app.tools.analyze photo1.jpg photo2.jpg --json resultat.json
uv run python -m app.tools.analyze --text lecon.txt          # sans OCR
uv run python -m app.tools.analyze photo.jpg --provider fake # démo hors ligne (leçon de référence)
```

L'outil affiche le texte lu, la leçon et ses notions, ce que les validateurs ont
rejeté, une première séance composée et le coût de chaque appel IA (jetons,
latence). `--json` enregistre le résultat complet pour l'évaluation (étape 5).
Formats acceptés : JPEG, PNG, WebP, GIF (convertir les photos HEIC d'iPhone).

## Vérifications (identiques à l'intégration continue)

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app tests
uv run pytest
```

Les tests utilisent un vrai PostgreSQL (base `ludifun_test`, remise à zéro à chaque lancement) :
ils vérifient notamment que les migrations correspondent aux modèles et que la suppression
d'un appareil efface toutes ses données.

## Modifier le schéma

1. Modifier `app/db/models.py`.
2. `uv run alembic revision --autogenerate -m "description"` puis relire le fichier généré dans `migrations/versions/`.
3. `uv run pytest` : `test_models_match_migrations` échoue si un changement n'a pas de migration.

## Configuration

Variables d'environnement (préfixe `LUDIFUN_`, ou fichier `.env`) :

| Variable | Défaut |
|---|---|
| `LUDIFUN_ENVIRONMENT` | `dev` (`prod` masque `/docs`) |
| `LUDIFUN_DATABASE_URL` | `postgresql+asyncpg://ludifun:ludifun@localhost:5432/ludifun` |
| `LUDIFUN_TEST_DATABASE_URL` | `postgresql+asyncpg://ludifun:ludifun@localhost:5432/ludifun_test` (tests) |
| `LUDIFUN_LOG_LEVEL` | `INFO` |
| `LUDIFUN_AI_PROVIDER` | `claude` (`fake` : réponses rejouées depuis `reference_lessons/`) |
| `LUDIFUN_AI_OCR_MODEL`, `…_ANALYSIS_MODEL`, `…_MATERIAL_MODEL` | `claude-opus-5` |
| `LUDIFUN_AI_OCR_EFFORT`, `…_ANALYSIS_EFFORT`, `…_MATERIAL_EFFORT` | `low`, `high`, `medium` |
| `LUDIFUN_MAX_LESSON_CHARS` | `20000` |
