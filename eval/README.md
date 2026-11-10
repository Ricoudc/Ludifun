# Évaluation sur de vraies leçons (étape 5)

> **Essai rapide à la maison (Windows)** : `Ludifun.bat`, choix 12 « Essayer l'IA sur mes vraies
> leçons ». Un dossier par leçon dans `eval\lessons` avec ses photos, **ou un PDF, un Word
> (.docx) ou un LibreOffice (.odt)** ; `expected.json` est facultatif. Pour chaque leçon,
> `eval\results\<date>\<leçon>.txt` montre le texte lu, les notions et leur **thème**, les
> **jeux possibles par notion** et la séance complète (🎲 : jeu du jour), comme dans
> l'application. Sans `expected.json`, le rapport ne mesure pas la justesse (matière, notions
> indispensables) : il montre seulement ce que l'application en fait.

But : vérifier que l'application transforme correctement une **vraie** leçon photographiée
en une séance pertinente, avant de construire l'application (cahier des charges §17).

## 1. Constituer le corpus

Un dossier par leçon dans `eval/lessons/` :

```
eval/lessons/
├── cm1_histoire_revolution/
│   ├── page1.jpg
│   ├── page2.jpg
│   └── expected.json
├── ce2_conjugaison_present/
│   ├── page1.jpg
│   └── expected.json
└── …
```

- Photos prises **au téléphone, dans des conditions réelles** (sur la table, lumière de la pièce, cahier un peu penché). Formats : JPEG, PNG, WebP. Les photos HEIC d'iPhone doivent être converties en JPEG (réglage iPhone : Appareil photo → Formats → « Le plus compatible »).
- Les pages sont lues dans l'ordre alphabétique des noms de fichiers : `page1.jpg`, `page2.jpg`…
- Pour tester l'analyse sans l'OCR, on peut mettre un `lesson.txt` à la place des photos.
- Premier objectif : **10 leçons**, puis 30 (répartition du §17.1 : niveaux, matières, supports manuscrits / manuels / photocopies). Ajouter 1 ou 2 **cas pièges** (photo qui n'est pas une leçon).

⚠️ **Données d'enfants** : `eval/lessons/` et `eval/results/` sont exclus du dépôt git (`.gitignore`). Avant de prendre les photos, masquer ou couper le nom de l'enfant et de l'école. Recueillir l'accord des familles et garder ces fichiers dans un espace privé.

## 2. Annoter chaque leçon : `expected.json`

Un adulte (enseignant ou parent) indique ce qu'un élève doit **forcément** savoir pour une interrogation :

```json
{
  "subject": "history",
  "grade": "CM1",
  "support": "cahier (manuscrit)",
  "essential": [
    { "label": "1789" },
    { "label": "Louis XVI" },
    { "label": "États généraux", "aliases": ["réunion des États généraux"] },
    { "label": "Prise de la Bastille" }
  ],
  "personal": ["Emma Martin", "École Jules Ferry"],
  "notes": "Leçon recopiée au tableau, écriture de l'enfant."
}
```

- `subject` : `french`, `math`, `history`, `geography`, `science`, `english`, `civics`, `other`.
- `grade` : `CP`, `CE1`, `CE2`, `CM1`, `CM2`, `6e`, `5e`, `4e`, `3e`.
- `essential` : 3 à 8 notions indispensables, avec leur nom le plus courant. `aliases` accepte d'autres façons de les nommer. La correspondance ignore la casse, les accents et les petites fautes.
- **Rappel des notions** : l'évaluateur associe les notions attendues et produites un-à-un. Une notion produite ne peut donc pas valider plusieurs notions attendues, même si son énoncé contient plusieurs libellés.
- `personal` (facultatif) : les noms écrits sur les pages (élève, école, enseignant). La lecture
  ne doit jamais les recopier ; le rapport compte ceux qui sont retrouvés dans le texte lu, sans
  jamais les écrire. C'est une mesure de l'analyse d'impact
  ([`docs/rgpd/aipd.md`](../docs/rgpd/aipd.md)) : **à remplir chaque fois qu'un nom est visible**
  sur la photo.
- Cas piège : `"is_lesson": false` et `"essential": []`.

Des exemples complets sont dans `eval/example/`. Le corpus de démonstration contient six leçons
de référence déterministes (CP, CE2, CM1, CM2, 6e et 3e) et un cas piège. Il sert à vérifier le
fonctionnement du rapport et les régressions logicielles ; **il ne remplace pas les dix premières
leçons réelles annotées** attendues dans `eval/lessons/`.

## 3. Lancer l'évaluation

```bash
cd backend
export ANTHROPIC_API_KEY=...        # ou `ant auth login`
uv run python -m app.tools.evaluate ../eval/lessons
```

Options : `--only lecon1,lecon2`, `--concurrency 3` (leçons en parallèle), `--provider fake` (démonstration hors ligne sur `eval/example`), `--prompt analysis=v7` (évaluer une ancienne version d'un prompt, répétable).

Quand la lecture d'une photo signale des passages douteux, l'application demanderait à l'enfant
« Peux-tu vérifier ? ». L'évaluation joue l'enfant qui confirme ce qui a été lu, puis
l'analyse reprend : ces passages sont comptés, et la leçon est quand même mesurée.

## 4. Rapport téléchargeable depuis GitHub Actions

À chaque CI backend de cette branche, après les tests PostgreSQL, le workflow exécute le corpus
synthétique avec le fournisseur déterministe `fake` et publie un artefact
`ludifun-quality-ai-benchmark` pendant 14 jours.

Dans GitHub : ouvrir **Actions → Backend → exécution réussie → Artifacts** et télécharger
`ludifun-quality-ai-benchmark`. L'archive contient le rapport Markdown, les métriques JSON,
les résultats JSON par leçon et les séances générées. Ce rapport vérifie le fonctionnement
reproductible de l'évaluateur ; il ne constitue pas une mesure de performance d'un modèle réel.

Pour produire le même rapport localement :

```bash
cd backend
uv run python -m app.tools.evaluate ../eval/example --provider fake --out ../artifacts/quality-ai
```

En plus des mesures du §17.2, le rapport suit ce qu'ont ajouté les étapes 13 à 15 :

| Mesure | Seuil |
|---|---|
| Photos à faire vérifier (passages douteux) | à suivre : trop de passages lassent l'enfant, trop peu laissent passer des erreurs de lecture |
| Notions reliées à une compétence | ≥ 90 % |
| Notions avec indice et rappel (« Je n'ai pas compris ») | ≥ 90 % |
| Questions ouvertes par leçon | ≥ 1 en moyenne |
| Notions importantes avec question ouverte | indicateur de suivi, selon pertinence pédagogique |
| Noms personnels dans le texte lu | 0 |

La couverture des questions ouvertes rapporte la part des notions d'importance 4 ou 5 qui
disposent d'au moins une question ouverte. Elle est affichée séparément du nombre brut de
questions : certaines notions importantes (date, nom ou fait à mémoriser) ne se prêtent pas
à une réponse rédigée. Cette couverture est donc informative et n'est pas un seuil automatique.

Chaque lancement crée `eval/results/<date-heure>/` :

| Fichier | Contenu |
|---|---|
| `report.md` | mesures du §17.2 avec les seuils (✅ / ❌), tableau par leçon, notions indispensables manquées |
| `<leçon>.txt` | ce que l'élève verrait : texte lu, notions, séance complète avec les réponses |
| `<leçon>.json` | tout le détail : texte OCR, analyse, matériel, éléments rejetés et raisons, appels IA (jetons, latence, coût) |
| `metrics.json` | les mesures et la configuration (fournisseur, modèles, version de chaque prompt), pour comparer deux évaluations |
| `open_questions_review.json` | questions ouvertes avec leur notion, son énoncé, le niveau, les points clés et la réponse modèle, prêtes pour une revue pédagogique humaine |

Le rapport détaille également le **rappel des notions indispensables par matière et par niveau**.
Ces tableaux sont calculés à partir des notions annotées et retrouvées (pondération par notion),
et non à partir d'une moyenne non pondérée des pourcentages de chaque leçon.

## 4. Revue de pertinence des questions ouvertes

Le fichier `open_questions_review.json` rassemble chaque question avec le contexte nécessaire
pour juger sa pertinence : notion visée, énoncé de la notion, importance, niveau cognitif,
consigne, points clés, réponse modèle et éventuel passage source. Il propose cinq axes de revue :

1. la question évalue bien la notion associée ;
2. le niveau annoncé (appliquer, expliquer, transférer) correspond à la tâche demandée ;
3. la question ne contient pas déjà sa réponse ;
4. les points clés et la réponse modèle sont cohérents ;
5. le vocabulaire et l'effort demandé conviennent à l'âge.

Ce fichier est une **grille de revue, pas un score automatique** : une correspondance de mots ne
suffit pas à prouver la pertinence pédagogique. Un adulte renseigne `review_status` avec
`pertinent`, `à corriger` ou `hors sujet`, puis conserve le fichier annoté séparément.
Les identifiants `review_id` permettent de rattacher les labels à la même notion et au même
rang de question. À la prochaine évaluation, réappliquer les labels et calculer les taux :

```bash
uv run python -m app.tools.evaluate ../eval/lessons --question-reviews ../eval/annotations/open_questions_review.json
```

Le rattachement vérifie aussi que l'énoncé n'a pas changé : une annotation périmée ou orpheline
fait échouer l'évaluation au lieu d'être attribuée silencieusement à une autre question. Les
questions non annotées restent hors du dénominateur. Le rapport et `metrics.json` indiquent le
nombre annoté, le nombre en attente, les trois catégories et les taux parmi les seules questions
annotées. Le benchmark ne doit annoncer de taux de pertinence qu'à partir de ces annotations humaines.

## 5. Évaluation humaine

Pour 10 leçons, un adulte relit `<leçon>.txt` (ou joue la séance) et remplit
[`grille-evaluation.md`](grille-evaluation.md). Ensuite, 5 enfants testent en situation réelle.

## 6. Améliorer, puis mesurer à nouveau

Les prompts sont dans `backend/app/ai/prompts/` et sont versionnés : `analysis.v1.md` devient `analysis.v2.md`, puis on met à jour `PROMPT_VERSIONS` dans `backend/app/ai/ports.py`. On relance ensuite l'évaluation **sur le même corpus**, puis on compare les deux résultats (§5.81) :

```bash
cd backend
uv run python -m app.tools.evaluate ../eval/lessons --prompt analysis=v7   # A : l'ancienne version
uv run python -m app.tools.evaluate ../eval/lessons                        # B : la nouvelle
uv run python -m app.tools.compare ../eval/results/<A> ../eval/results/<B> --out ../eval/results/comparaison.md
```

Sur le PC de la famille (Docker) :

```powershell
docker compose run --rm --no-deps -v "${PWD}\eval:/eval" api python -m app.tools.compare /eval/results/<A> /eval/results/<B>
```

La comparaison met les mesures côte à côte (◀ A, B ▶ ou =), compare leçon par leçon, puis
conclut : la justesse d'abord (leçons traitées, rappel des notions, notions inventées, noms
personnels, matériel rejeté), la durée et le coût ensuite. Elle dit quoi remettre pour revenir à
la configuration retenue (version de prompt dans `PROMPT_VERSIONS`, fournisseur, modèle). Les
modèles et l'effort de chaque étape se changent sans toucher au code (variables `LUDIFUN_AI_*`,
voir `backend/README.md`), ce qui permet de comparer aussi deux modèles. Relire quelques séances
des deux côtés avant de trancher : les chiffres ne voient pas tout.
