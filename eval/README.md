# Évaluation sur de vraies leçons (étape 5)

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
  "notes": "Leçon recopiée au tableau, écriture de l'enfant."
}
```

- `subject` : `french`, `math`, `history`, `geography`, `science`, `english`, `civics`, `other`.
- `grade` : `CP`, `CE1`, `CE2`, `CM1`, `CM2`, `6e`, `5e`, `4e`, `3e`.
- `essential` : 3 à 8 notions indispensables, avec leur nom le plus courant. `aliases` accepte d'autres façons de les nommer. La correspondance ignore la casse, les accents et les petites fautes.
- Cas piège : `"is_lesson": false` et `"essential": []`.

Des exemples complets sont dans `eval/example/`.

## 3. Lancer l'évaluation

```bash
cd backend
export ANTHROPIC_API_KEY=...        # ou `ant auth login`
uv run python -m app.tools.evaluate ../eval/lessons
```

Options : `--only lecon1,lecon2`, `--concurrency 3` (leçons en parallèle), `--provider fake` (démonstration hors ligne sur `eval/example`).

Chaque lancement crée `eval/results/<date-heure>/` :

| Fichier | Contenu |
|---|---|
| `report.md` | mesures du §17.2 avec les seuils (✅ / ❌), tableau par leçon, notions indispensables manquées |
| `<leçon>.txt` | ce que l'élève verrait : texte lu, notions, séance complète avec les réponses |
| `<leçon>.json` | tout le détail : texte OCR, analyse, matériel, éléments rejetés et raisons, appels IA (jetons, latence, coût) |

## 4. Évaluation humaine

Pour 10 leçons, un adulte relit `<leçon>.txt` (ou joue la séance) et remplit
[`grille-evaluation.md`](grille-evaluation.md). Ensuite, 5 enfants testent en situation réelle.

## 5. Améliorer, puis mesurer à nouveau

Les prompts sont dans `backend/app/ai/prompts/` et sont versionnés : `analysis.v1.md` devient `analysis.v2.md`, puis on met à jour `PROMPT_VERSIONS` dans `backend/app/ai/ports.py`. On relance ensuite l'évaluation **sur le même corpus** et on compare les deux `report.md`. Les modèles et l'effort de chaque étape se changent sans toucher au code (variables `LUDIFUN_AI_*`, voir `backend/README.md`), ce qui permet de comparer coût et qualité.
