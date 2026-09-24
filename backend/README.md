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

## API

Documentation interactive : http://localhost:8000/docs. Parcours type :

```bash
# Parent : compte, enfant, code de liaison
curl -s -X POST localhost:8000/v1/auth/register -H 'content-type: application/json' \
  -d '{"email":"parent@example.fr","password":"un mot de passe solide","accepted_privacy_policy":true}'
curl -s -X POST localhost:8000/v1/children -H "authorization: Bearer $ACCESS" -H 'content-type: application/json' \
  -d '{"display_name":"Emma","grade":"CM1","parental_consent":true}'
curl -s -X POST localhost:8000/v1/children/$CHILD/link-codes -H "authorization: Bearer $ACCESS"
# Appareil de l'enfant : saisie du code
curl -s -X POST localhost:8000/v1/link -H 'content-type: application/json' -d '{"code":"482731"}'
# L'enfant envoie sa leçon, suit l'analyse, puis révise
curl -s -X POST localhost:8000/v1/lessons -H "authorization: Bearer $DEVICE" -F pages=@page1.jpg -F pages=@page2.jpg
curl -s localhost:8000/v1/lessons/$LESSON -H "authorization: Bearer $DEVICE"            # statut, puis notions
curl -s -X POST localhost:8000/v1/lessons/$LESSON/sessions -H "authorization: Bearer $DEVICE" -H 'content-type: application/json' -d '{}'
# Espace parent : tableau de bord et historique
curl -s "localhost:8000/v1/children/$CHILD/dashboard?weeks=4" -H "authorization: Bearer $ACCESS"
curl -s "localhost:8000/v1/children/$CHILD/history?limit=20" -H "authorization: Bearer $ACCESS"
curl -s "localhost:8000/v1/children/$CHILD/skills" -H "authorization: Bearer $ACCESS"   # compétences, niveaux 0-5
```

Sans clé d'API, lancer l'API avec `LUDIFUN_AI_PROVIDER=fake` : toute photo est lue comme la leçon d'histoire de référence.

## Famille de démonstration

Pour voir l'application remplie dès le premier lancement (développement uniquement, refusé en production) :

```bash
uv run python -m app.tools.demo_family                        # base locale
docker compose exec api python -m app.tools.demo_family       # pile docker compose
uv run python -m app.tools.demo_family --replace              # recrée le compte s'il existe
```

L'outil crée le compte `parent.demo@example.fr` (mot de passe `demo-ludifun-2026`, modifiables
avec `--email` et `--password`), avec deux enfants :

- **Emma** (CM1) : sa tablette de démonstration a révisé les trois leçons de référence
  (histoire, fractions, états de l'eau) pendant quatre semaines, avec des erreurs qui se
  corrigent peu à peu. Tableau de bord, historique et mission du jour montrent donc de vraies
  données, calculées par l'API ;
- **Hugo** (CE1) : profil vide, sans appareil.

Il affiche aussi un code (valable 10 minutes) pour lier un vrai téléphone au profil d'Emma et
jouer ses révisions. Les leçons passent par l'IA factice : aucun appel payant. Les séances sont
jouées par l'API elle-même, avec un « élève simulé » (`app/domain/simulated_pupil.py`) et une
horloge simulée.

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
| `LUDIFUN_AI_EVALUATION_MODEL`, `…_EVALUATION_EFFORT` | `claude-sonnet-5`, `low` : correction des réponses rédigées, pendant la séance |
| `LUDIFUN_MAX_LESSON_CHARS` | `20000` |
| `LUDIFUN_AI_DAILY_BUDGET_USD` | `50` : plafond de dépense IA par jour (UTC), tous comptes confondus ; vide = sans plafond |
| `LUDIFUN_JWT_SECRET` | secret de développement ; **obligatoire en production** (l'API refuse de démarrer sans) |
| `LUDIFUN_ACCESS_TOKEN_MINUTES`, `…_REFRESH_TOKEN_DAYS` | `15`, `30` |
| `LUDIFUN_LINK_CODE_MINUTES`, `…_PASSWORD_RESET_MINUTES` | `10`, `60` |
| `LUDIFUN_PASSWORD_RESET_URL` | `ludifun://app/parent/nouveau-mot-de-passe?jeton=` (le jeton est ajouté à la fin) |
| `LUDIFUN_FAMILY_TIMEZONE` | `Europe/Paris` (découpage en semaines du tableau de bord parent) |
