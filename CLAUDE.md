# Règles de travail pour les IA de développement (Ludifun)

Coach de révision pour élèves du CP à la 3e : un espace parent et un espace enfant. Serveur
FastAPI + PostgreSQL (`backend/`), application Flutter (`mobile/`). Tout est en français : textes
de l'application, documentation, commentaires, messages de commit.

## Avant toute modification

1. Lire le cahier des charges (`docs/cahier-des-charges-complet.md`), en particulier les
   directives pour l'IA de développement (§112-149), et la spécification technique
   (`docs/specification-technique.md` : ce qui est construit, étape par étape ; §11 : état de
   conformité aux §112-149).
2. Chercher ce qui existe déjà : ne pas recréer une fonctionnalité, un service ou une activité.
3. Annoncer : objectif, fichiers concernés, impact, plan, risques, tests prévus (§134).

## Architecture à respecter

- `APPLICATION → MOTEUR PÉDAGOGIQUE → SERVICES IA`, jamais `APPLICATION → LLM → réponse` (§112).
  Le LLM propose (analyse d'une leçon, matériel, correction d'une réponse rédigée) ; le code
  décide (`backend/app/domain/` : maîtrise, niveaux, choix des activités, notation, révisions,
  remédiation). Le domaine reste pur : pas de base, pas de réseau, déterministe pour une graine.
- Toute sortie de l'IA passe par un schéma puis par les contrôles de `app/domain/validation.py`
  avant d'être enregistrée ; un échec ne doit jamais toucher la progression de l'enfant.
- Texte de leçon et réponse d'enfant = données entre balises, jamais des consignes (§142-143).
- Nouvelle activité : une classe `ActivityType` + `default_registry()` + élève simulé + widget
  dans `mobile/lib/features/session/activities/activity_registry.dart`.
- Prompts versionnés (`app/ai/prompts/<étape>.vN.md`) : on en ajoute une version, on ne réécrit
  pas le sens d'une version déjà utilisée.

## Ne pas casser l'existant (§133)

- Contrats d'API : pas de champ retiré ni renommé ; l'application publiée doit continuer de
  fonctionner (un type d'activité inconnu est sauté, un champ nouveau est facultatif).
- Base de données : toute modification passe par une migration Alembic numérotée
  (`backend/migrations/versions/AAAAMMJJ_00NN_*.py`), avec reprise des données existantes et test dans
  `tests/db/test_schema.py` ; mettre à jour la version attendue par `/health/ready`.
- Séparation parent / enfant stricte : un jeton d'enfant n'accède qu'à ses données, un parent
  qu'à sa famille (tests dans `tests/api/test_separation.py`).

## Vérifications avant de dire « terminé »

Serveur (`backend/`, PostgreSQL local : `service postgresql start` si la connexion est refusée) :

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy app tests && uv run pytest -q
```

Application (`mobile/`) :

```bash
dart format lib test && flutter analyze && flutter test
```

Scripts Windows (`scripts/windows/*.ps1`) : UTF-8 avec BOM et fins de ligne CRLF ; `.env` écrit
en UTF-8 sans BOM.

Après la modification : modifications effectuées, tests réalisés, résultats, problèmes
restants. Ne jamais dire qu'une fonctionnalité marche si elle n'a pas été testée (§134) ; dire
ce qui n'a pas pu l'être (téléphone réel, Windows, vraie IA).

## Données et secrets

- Jamais de clé d'API, de `.env`, de photo ni de leçon d'enfant dans le dépôt
  (`eval/lessons/`, `eval/results/` sont ignorés). Les photos ne sont jamais stockées côté serveur.
- Journaux et page `/suivi` : données techniques seulement (pas de prénom, pas de texte de leçon).
- Clés d'IA des familles chiffrées (Fernet), jamais renvoyées à l'application.
