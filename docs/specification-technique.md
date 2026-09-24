# Spécification technique — du cahier des charges complet au code

> Traduit le [cahier des charges complet](cahier-des-charges-complet.md) (« CDC §n ») en travaux
> de développement, **à partir de ce qui est déjà construit et testé** (étapes 1 à 12 du
> [cahier des charges V1](cahier-des-charges-v1.md), « V1 §n »). Le projet n'est pas refait :
> l'architecture en place (Flutter, FastAPI, PostgreSQL, IA derrière des interfaces) est celle
> que demande le CDC (§49-§52, §60, §92) ; on l'étend.

---

## 1. Point de départ : ce qui existe déjà

État au commit `0e58b44` (pull request #1), avant l'étape 13 : 424 tests serveur, 51 tests
application, intégration continue verte, APK Android de test. Les lignes marquées « étape 13 »
ont été mises à jour depuis.

| CDC | Exigence | État | Où |
|---|---|---|---|
| §5-§6 | Espaces parent et enfant, plusieurs enfants, code à 6 chiffres et QR code, séparation stricte | ✅ | `api/v1/children.py`, `features/parent`, `features/link` ; tests de séparation |
| §8.1-8.3 | Photo, galerie, plusieurs pages réordonnables | ✅ | `features/capture` |
| §8.4 | PDF | ⏳ V1.5 | — |
| §8.5 | Texte collé ou saisi | 🟡 le pipeline sait partir d'un texte (relance) ; pas de route ni d'écran | étape 15 |
| §9 | OCR et vision multimodale | ✅ texte, titres, tableaux, formules ; 🟡 schémas et cartes décrits, pas exploités | `ai/ocr/vision_llm.py` |
| §10 | Ne jamais inventer ; faire vérifier une lecture incertaine | 🟡 citation source obligatoire par notion (vérifiée à 90 %), qualité par page ; pas de vérification par l'enfant | étape 15 |
| §11-§12 | Analyse pédagogique, modèle de connaissance structuré | ✅ notions typées (10 types), importance 1-5, relations, citation | `domain/knowledge.py`, `prompts/analysis.v2.md` |
| §11, §13 | Compétences | ✅ étape 13 : extraites par l'analyse, reliées aux notions, niveau affiché | `domain/knowledge.py` (`Skill`), tables `skills`, `skill_knowledge` |
| §14 | Maîtrise 0-5 | ✅ étape 13 : niveau 0-5 par notion et par compétence, avec explication | `domain/understanding.py` |
| §15, §65 | Mémorisation vs compréhension, transfert | ✅ étapes 13-14 : niveaux 1 reconnaître, 2 se rappeler, 3 appliquer (exigés), 4 expliquer et 5 transférer (questions ouvertes d'approfondissement) | `domain/understanding.py` |
| §16-§18 | Moteur qui choisit l'activité ; QCM, vrai/faux, flashcards, texte à trous, association, défi rapide | ✅ 6 activités, composition par blocs selon la maîtrise | `domain/composer.py`, `domain/activities/` |
| §18 | Questions ouvertes, memory, classement | ✅ questions ouvertes (étape 14) ; ⏳ `MEMORY`, `ORDER` déclarés | `domain/activities/open_question.py` ; V2 |
| §19-§25 | Pratique par matière, activités visuelles, géographie, histoire, sciences, maths | ⏳ V2-V3 | §9 de ce document |
| §26, §83 | Oral, « Enseigne-moi » | 🔮 V4 | |
| §27-§28 | « Je n'ai pas compris » (5 niveaux), langage adapté à l'âge | ✅ étape 14 : indice, rappel, exemple, étapes, réponse | `domain/help.py`, `features/session/help_sheet.dart` |
| §29 | Mode devoirs | 🔮 V3 | |
| §31 | Durée de séance choisie par le parent | 🟡 durée estimée affichée ; pas de durée cible | étape 16 |
| §32 | Fatigue / désengagement | ⏳ | étape 17 |
| §33 | Plan de révision avant un contrôle | ⏳ | étape 16 |
| §34 | Répétition espacée | ✅ J+1, 2, 4, 7, 14 selon la réussite ; mission du jour | `domain/mastery.py` |
| §35-§36 | Adaptation en temps réel, difficulté dynamique | 🟡 reprise des erreurs en fin de séance ; difficulté 1-3 selon la maîtrise | étape 17 |
| §37-§39, §85 | Missions, XP, badges, séries | 🟡 « mission du jour » ; pas d'XP ni de badges | V2 |
| §40-§42 | Tableaux de bord enfant et parent, statuts 🟢🟠🔴 | ✅ | `features/home`, `features/parent/child_dashboard_screen.dart` |
| §43, §62-§63 | Historique des erreurs, types d'erreurs | ✅ étape 14 : type d'erreur par notion ratée, erreurs récurrentes au tableau de bord | `domain/errors.py` |
| §44-§45 | Historique, graphiques | ✅ historique paginé, progression par semaine | `services/dashboard.py` |
| §46 | Assistant parent | 🔮 V5 | |
| §47 | Objectifs parent | ⏳ | étape 16 |
| §48 | Notifications | 🔮 V5 | |
| §59-§61, §68 | IA en étapes, fournisseur interchangeable, contrats JSON stricts, contrôle qualité | ✅ lecture → analyse → matériel par notion, schémas Pydantic, validateurs, relance ciblée, `ai_runs` | `ai/`, `services/lesson_pipeline.py` |
| §69-§70 | Sécurité, RGPD (effacement, export, consentement, minimisation) | ✅ côté code ; reste l'hébergement et les documents (README) | V1 §16 |
| §71 | Conservation des photos | ✅ mode temporaire uniquement (jamais stockées) | voir arbitrage A3 |
| §73 | Pas de publicité | ✅ | |
| §88 | Hors connexion | 🔮 | |
| §90-§91 | Observabilité, coûts IA | ✅ `ai_runs` (jetons, latence, statut), plafond journalier | `services/ai_budget.py` |
| §93 | Tests fonctionnels et IA | ✅ ; 🟡 tests pédagogiques sur vraies leçons (étape 5 en attente) | `tools/evaluate.py` |

**Lecture** : le « MVP » du CDC (§95) est atteint à l'exception de quatre points — les
**compétences**, l'**aide** progressive, les **questions ouvertes** et les **types d'erreurs**.
Ce sont les étapes 13 et 14, avant les tests avec de vraies familles.

---

## 2. Arbitrages

| # | Sujet | CDC | Proposition | Statut |
|---|---|---|---|---|
| A1 | Âge de l'enfant | §54 : `birth_year` | **Garder la classe seule** : elle suffit pour adapter le langage (§28) et évite une donnée personnelle (minimisation, V1 §16.2). | à valider |
| A2 | Nom du parent | §6.1 : « éventuellement nom » | E-mail seul ; un prénom facultatif pour les messages. | à valider |
| A3 | Photos | §71 : mode historique au choix du parent | Garder le **mode temporaire** par défaut. Le mode historique (stockage chiffré, suppression avec la leçon, opt-in explicite) viendra avec l'hébergement UE, pas avant. | à valider |
| A4 | Maîtrise 0-5 | §14 | Conserver le score interne 0-100 (plus fin) et **afficher** le niveau 0-5 calculé (§5.3). | proposé |
| A5 | Intervalles | §34 : J1, J3, J7, J14 | Déjà J+1, 2, 4, 7, 14 selon la réussite : conforme à l'esprit, pas de changement. | proposé |
| A6 | Adaptation | §31, §109 : réussite → plus difficile, difficulté → aide | Conforme à ce qui est codé (question ouverte depuis l'étape 5 : **tranchée par le CDC**). | ✅ |
| A7 | Routes de l'API | §58 : `/families`, `/activities/generate`, `/answers`… | Garder les routes existantes (même rôle, déjà testées) : `/children`, `/lessons/{id}/sessions`, `/sessions/{id}/attempts`… Nouvelles routes au §7. | proposé |
| A8 | Orchestrateur IA | §59 : 12 « agents » | Des **étapes** au contrat strict, pas des agents autonomes : lecture, analyse, matériel (existants), puis évaluation des réponses ouvertes, aides, assistant parent. La planification, l'adaptation et la révision restent **déterministes** (moteur pédagogique, §92). | proposé |
| A9 | Modèles de repli | — | Garder le basculement automatique vers un autre modèle en cas de refus. | question ouverte |

---

## 3. Architecture (évolution)

```
backend/app/
├── domain/                     # pur Python, sans infrastructure (test d'architecture)
│   ├── knowledge.py            # + Skill, SkillVerb (étape 13 ✅)
│   ├── understanding.py        # niveaux de compréhension, niveau affiché 0-5 (étape 13 ✅)
│   ├── help.py                 # aide progressive (§27) (étape 14 ✅)
│   ├── errors.py               # types d'erreurs, erreurs récurrentes (§43, §63) (étape 14 ✅)
│   ├── remediation.py          # NOUVEAU : adaptation en temps réel (§35)
│   ├── engagement.py           # NOUVEAU : signaux de fatigue (§32)
│   ├── planning.py             # NOUVEAU : séance à durée cible, plan avant contrôle (§31, §33)
│   ├── composer.py             # + durée cible, niveaux de compréhension
│   └── activities/             # + open_question.py (étape 14 ✅), order.py, memory.py
├── ai/prompts/                 # analysis.v2 (compétences, ✅), material.v2 (aides, erreurs types, ✅),
│                               # ocr.v2 (passages incertains), evaluation.v1 (réponses ouvertes, ✅)
├── services/                   # goals.py, revision_plans.py (NOUVEAUX)
└── api/v1/                     # goals.py, help (dans sessions.py), review (dans lessons.py)

mobile/lib/
├── app/level_stars.dart                   # niveau 0-5 en étoiles (étape 13 ✅)
├── features/parent/child_skills_screen.dart  # compétences par leçon (étape 13 ✅)
└── features/
├── session/help_sheet.dart     # « ❓ Je n'ai pas compris »
├── session/activities/         # + open_question_view, order_view, memory_view
├── analysis/ocr_review_screen.dart   # « Peux-tu vérifier ? »
├── capture/text_import_screen.dart   # coller une leçon
└── parent/goals_screen.dart          # temps quotidien, date de contrôle, plan
```

---

## 4. Modèle de données

### 4.1 Migration `0003` (étape 13, faite)

```sql
-- Compétences d'une leçon (CDC §11, §13), reliées aux notions qu'elles mobilisent.
CREATE TABLE skills (
    id             UUID PRIMARY KEY,
    lesson_id      UUID NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    key            TEXT NOT NULL,               -- "s1", "s2"… (comme les notions "k1")
    label          TEXT NOT NULL,               -- « Comparer deux fractions »
    verb           TEXT NOT NULL CHECK (verb IN ('recognize','recall','apply','explain','transfer')),
    importance     SMALLINT NOT NULL CHECK (importance BETWEEN 1 AND 5),
    source_excerpt TEXT NOT NULL,               -- citation exacte, comme pour les notions
    position       SMALLINT NOT NULL,
    UNIQUE (lesson_id, key)
);
CREATE TABLE skill_knowledge (
    skill_id     UUID REFERENCES skills(id) ON DELETE CASCADE,
    knowledge_id UUID REFERENCES knowledge_items(id) ON DELETE CASCADE,
    PRIMARY KEY (skill_id, knowledge_id)
);

-- Niveau de compréhension sollicité par une activité (CDC §15).
ALTER TABLE session_items ADD COLUMN cognitive_level SMALLINT NOT NULL DEFAULT 1
    CHECK (cognitive_level BETWEEN 1 AND 5);
-- Niveaux à valider pour « maîtrisée », fixés à l'analyse d'après le matériel (§5.2).
ALTER TABLE knowledge_items ADD COLUMN required_levels SMALLINT[] NOT NULL DEFAULT '{1}';
-- Niveaux déjà validés par l'enfant.
ALTER TABLE knowledge_mastery ADD COLUMN levels SMALLINT[] NOT NULL DEFAULT '{}';
```

Les données existantes sont complétées par la migration (niveau de chaque activité, niveaux
exigés d'après le matériel, niveaux validés d'après les réponses des séances terminées). Le niveau
d'une compétence n'est pas stocké : il se calcule à partir de ses notions (§5.3), ce qui évite
une table `skill_mastery` à tenir à jour.

### 4.2 Migration `0004` (étape 14, faite)

```sql
-- L'aide est demandée avant la réponse : elle est portée par l'activité, pas par la tentative.
ALTER TABLE session_items ADD COLUMN help_level SMALLINT NOT NULL DEFAULT 0
    CHECK (help_level BETWEEN 0 AND 5);             -- aide la plus forte demandée
ALTER TABLE attempt_evidence ADD COLUMN error_type TEXT CHECK (error_type IN (
    'knowledge','calculation','method','reading','confusion',
    'forgotten','imprecision','random','statement')); -- NULL si réussi
-- Nouvelle étape IA journalisée : 'evaluation' dans ai_runs.stage.
```

La confiance de l'évaluateur n'est pas stockée : sous 0,4, sa correction est écartée (§6.4).

### 4.3 Prévu (étapes 15 à 17)

```sql
-- Étape 15 — source d'une leçon et relecture de l'OCR (CDC §8.5, §10).
ALTER TABLE lessons ADD COLUMN source TEXT NOT NULL DEFAULT 'camera'
    CHECK (source IN ('camera','gallery','text','pdf'));
-- + statut 'needs_review' dans lessons.status
CREATE TABLE lesson_review_items (
    id          UUID PRIMARY KEY,
    lesson_id   UUID NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    page_index  SMALLINT NOT NULL,
    read_text   TEXT NOT NULL,                  -- ce que l'OCR croit avoir lu
    box         REAL[4],                        -- zone de la page (0-1), pour zoomer
    answer      TEXT,                           -- confirmé / corrigé par l'enfant
    answered_at TIMESTAMPTZ
);

-- Étape 16 — objectifs et plans de révision (CDC §31, §33, §47).
CREATE TABLE goals (
    id              UUID PRIMARY KEY,
    child_id        UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL CHECK (kind IN ('daily_time','exam','subject_priority')),
    minutes_per_day SMALLINT CHECK (minutes_per_day IN (5,10,15,20,30)),
    subject         TEXT,
    lesson_ids      UUID[] NOT NULL DEFAULT '{}',
    due_date        DATE,                       -- date du contrôle
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    archived_at     TIMESTAMPTZ
);
CREATE TABLE revision_plan_days (
    goal_id   UUID REFERENCES goals(id) ON DELETE CASCADE,
    day       DATE NOT NULL,
    focus     TEXT NOT NULL CHECK (focus IN ('diagnostic','targeted','memorize','errors','mock_test')),
    minutes   SMALLINT NOT NULL,
    done_session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
    PRIMARY KEY (goal_id, day)
);

-- Étape 17 — difficulté intrinsèque d'une notion (CDC §36, §56).
ALTER TABLE knowledge_items ADD COLUMN difficulty SMALLINT NOT NULL DEFAULT 2
    CHECK (difficulty BETWEEN 1 AND 3);
```

V2 (gamification, CDC §37-§39) : `xp_events(child_id, reason, points, session_id, created_at)`,
`badges(child_id, code, earned_at)`, série calculée depuis `sessions`. Aucune
donnée de classement entre enfants (CDC §108.8).

---

## 5. Moteur pédagogique v2

### 5.1 Niveaux de compréhension des activités (CDC §15)

| Niveau | Activités | Évaluation |
|---|---|---|
| 1 Reconnaître | QCM (difficultés 1 et 2), vrai/faux, association, défi rapide ; memory (V2) | déterministe |
| 2 Se rappeler | texte à trous, carte mémoire (auto-évaluée, poids réduit) | déterministe (tolérance aux fautes) |
| 3 Appliquer | QCM de difficulté 3 (« relier, appliquer ») ; question ouverte « applique » ; classement, calcul (plus tard) | déterministe ou IA |
| 4 Expliquer | question ouverte « explique pourquoi » | IA (§6.4), mots clés en secours |
| 5 Transférer | question ouverte en situation nouvelle | IA (§6.4), mots clés en secours |

Question ouverte : difficulté 1, 2, 3 ↔ niveau 3, 4, 5 (la base garde la contrainte de
difficulté 1-3).

Le niveau de chaque activité est enregistré (`session_items.cognitive_level`). En révision, une
notion dont le score atteint 50 est travaillée à son **premier niveau exigé non validé** ; en
dessous, la difficulté suit le score comme avant. Une notion n'est plus mise de côté comme
« connue » tant qu'un niveau exigé manque, et sa priorité est calculée comme si son score était
d'au plus 70.

### 5.2 Niveaux exigés et niveaux validés

- **Exigés** (`knowledge_items.required_levels`, fixés à l'analyse) : les niveaux que le matériel
  de la leçon permet vraiment de travailler, jusqu'au plafond du type de notion — 3 pour une règle,
  une formule ou un processus (elles s'appliquent), 2 pour les autres. On n'exige jamais un niveau
  qu'aucune activité ne peut prouver (une classification sans texte à trous ni carte : niveau 1).
- **Validés** (`knowledge_mastery.levels`) : un niveau est validé quand, dans une séance, le taux
  pondéré des réponses de ce niveau atteint 80 % (reprise des erreurs comprise). Un niveau validé
  le reste.
- Le score 0-100, les boîtes et les intervalles de révision ne changent pas. L'aide demandée
  réduit la preuve (§5.4) ; une réponse donnée après l'exemple ou la solution ne valide pas de
  niveau.
- **Approfondir** (étape 14) : une notion maîtrisée à tous ses niveaux exigés, dont la révision
  est due et le score ≥ 80, reçoit une question ouverte de niveau 4 (expliquer) puis 5
  (transférer) quand la leçon en a. Ces niveaux enrichissent la maîtrise sans être exigés. Une
  question ouverte n'est jamais proposée « par défaut » (première séance, reprise des erreurs).

### 5.3 Niveau affiché 0-5 (CDC §14, arbitrage A4)

| Niveau | Règle |
|---|---|
| 0 Jamais travaillée | aucune réponse |
| 1 Découverte | score < 30 |
| 2 Fragile | score 30-49 |
| 3 En cours d'acquisition | score 50-79, ou ≥ 80 **sans tous les niveaux exigés** (CDC §65) |
| 4 Maîtrisée | score ≥ 80 et tous les niveaux exigés validés |
| 5 Très bien maîtrisée | niveau 4, score ≥ 90, et tenu jusqu'à la dernière boîte de révision (J+14) |

Une leçon est « maîtrisée » quand toutes ses notions importantes sont au niveau 5.

**Compétence** : moyenne des niveaux de ses notions arrondie vers le bas, et au plus un niveau
au-dessus de sa notion la plus faible (une notion fragile suffit à laisser la compétence « en
cours »).

Statuts parent (CDC §42) : 🟢 niveaux 4-5, 🟠 niveau 3, 🔴 niveaux 1-2, ⚪ 0, toujours avec la
phrase qui explique pourquoi : « Reconnaît la bonne réponse, pas encore la retrouver seul. »,
« Connaît la règle, doit encore s'entraîner à l'appliquer. »… « À renforcer » du tableau de bord
liste les notions de niveau 3 ou moins, même réussies à 100 % en QCM.

### 5.4 Aide progressive (CDC §27)

Chaque notion reçoit à l'analyse ses aides graduées (§6.2) : indice → rappel → exemple
semblable → étapes ; le niveau 5 est la réponse de l'activité elle-même, avec son explication.
Chaque appui sur « ❓ Je n'ai pas compris » renvoie l'aide suivante. Avant le niveau 5, une aide
qui dévoilerait la réponse de l'activité est **sautée** (vérifié au moment de la montrer : mots de
la réponse, pluriel, faute) ; une aide absente aussi. Leçons d'avant l'étape 14 : l'astuce sert
d'indice, l'énoncé d'une règle sert de rappel. Proposée pour les activités sur une seule notion
(pas l'association ni le défi rapide).

Le niveau atteint est enregistré (`session_items.help_level`). L'aide n'est jamais punie à
l'écran (la note de la séance ne change pas) ; pour la maîtrise, le résultat est multiplié par
1 (indice, rappel), 0,75 (exemple), 0,5 (étapes), 0 (réponse vue).

### 5.5 Types d'erreurs (CDC §43, §63)

- **QCM et vrai/faux** : chaque distracteur porte, dès la génération, le type d'erreur qu'il
  révèle (`misconception`, §6.2) ; choisir ce distracteur donne ce type.
  Sans type indiqué (leçons d'avant l'étape 14, vrai/faux) : `knowledge`.
- **Texte à trous** : réponse proche mais hors tolérance → `imprecision` ; vide ou « je ne sais
  pas » → `forgotten` ; sinon `knowledge` (la confusion avec une autre notion viendra plus tard).
- **Carte mémoire** « je ne savais pas » → `forgotten` ; **association** ratée → `confusion` ;
  **défi rapide** → `knowledge`.
- **Réponses très rapides et fausses** (< 1,5 s, sans aide, activité sur une notion) → `random`.
- **Questions ouvertes** : type donné par l'évaluateur IA (§6.4) ; en secours, `forgotten`,
  `imprecision` ou `knowledge` selon les points clés trouvés.
- **Erreur récurrente** : même type d'erreur sur la même notion dans 3 séances distinctes (60
  derniers jours ; les réponses au hasard ne comptent pas) → signalée au parent dans le tableau de
  bord, avec les types d'erreurs des 30 derniers jours.

### 5.6 Adaptation en temps réel (CDC §35)

Deux échecs sur la même notion dans une séance → le serveur **insère** après l'activité en
cours une mini-séquence de remédiation : carte « rappel de la règle » (sans note) → activité
facile de niveau 1 → activité normale ; la suite de la séance reprend ensuite. Réponse de
`POST /sessions/{id}/attempts` : champ `inserted_items` (le client les intercale).

### 5.7 Engagement (CDC §32, sans diagnostic)

Signaux sur les 5 dernières réponses : 3 réponses fausses en moins de 1,5 s ; temps de réponse
×2 par rapport à la médiane de l'enfant ; 3 échecs consécutifs ; 2 activités « passées ».
→ `engagement_hint` dans la réponse : `pause` (« On fait une petite pause ? ») ou `switch`
(changer de type d'activité pour les éléments suivants). Seuils en constantes, testés.

### 5.8 Séance à durée cible (CDC §31)

`POST /lessons/{id}/sessions {"target_minutes": 10}` (ou objectif quotidien du parent) : le
composeur remplit la durée à partir des durées estimées par type d'activité ; si l'enfant va
plus vite que prévu, `POST /sessions/{id}/extend` ajoute des activités de niveau supérieur.

### 5.9 Plan avant un contrôle (CDC §33)

Déterministe, à partir de la date du contrôle et des leçons choisies :

| Jours restants | Plan |
|---|---|
| ≥ 5 | diagnostic → exercices ciblés → mémorisation → révision des erreurs → mini-évaluation, puis révision espacée |
| 2-4 | diagnostic → ciblé + erreurs → mini-évaluation |
| 1 | séance complète + mini-évaluation |

Chaque jour est recalculé après la séance : une notion ratée au diagnostic passe devant ; une
journée manquée est redistribuée.

---

## 6. Contrats JSON de l'IA (versions 2)

Tous les appels restent des sorties structurées validées par Pydantic, avec relance ciblée
(§4 V1). Nouveaux champs ou appels :

### 6.1 Analyse v2 (+ compétences)

```json
{
  "skills": [
    {"id": "s1", "label": "Comparer deux fractions de même dénominateur", "verb": "apply",
     "importance": 5, "knowledge_ids": ["k2", "k3"],
     "source_excerpt": "Si deux fractions ont le même dénominateur…"}
  ],
  "knowledge": [{"id": "k2", "…": "…", "difficulty": 2}]
}
```

Validation : chaque compétence cite la leçon (même règle que les notions) et relie au moins
une notion existante.

### 6.2 Matériel v2 (+ aides, erreurs types, questions ouvertes)

```json
{
  "knowledge_id": "k2",
  "questions": [{"difficulty": 1, "stem": "…", "answer": "…",
                 "distractors": [{"text": "…", "misconception": "confusion"}]}],
  "help": {
    "hint": "Regarde le nombre du bas.",
    "reminder": "Le dénominateur indique en combien de parts on coupe l'unité.",
    "example": {"question": "3/8 ou 5/8 ?", "answer": "5/8", "why": "…"},
    "steps": ["…", "…"],
    "solution": "…"
  },
  "open_questions": [
    {"level": 4, "prompt": "Explique pourquoi 5/8 est plus grand que 3/8.",
     "key_points": ["même dénominateur", "on compare les numérateurs", "5 > 3"],
     "model_answer": "…"}
  ]
}
```

### 6.3 OCR v2 (+ passages incertains, CDC §10)

```json
{"pages": [{"index": 0, "quality": "partial", "text": "…",
            "uncertain": [{"text": "l'Assemblée constituante", "box": [0.12, 0.40, 0.70, 0.46]}]}]}
```

Au moins un passage incertain qui touche une notion importante → statut `needs_review` :
l'enfant confirme ou corrige chaque passage (zoom sur `box`, photo encore sur le téléphone),
puis l'analyse continue.

### 6.4 Évaluation d'une réponse ouverte (nouvel appel)

Entrée : la question, les `key_points`, la réponse de l'enfant, la classe. Pas l'historique ni
la leçon entière (CDC §91). Effort faible, 2-5 s.

```json
{"score": 0.67, "key_points_found": ["même dénominateur", "5 > 3"],
 "missing": ["on compare les numérateurs"], "error_type": "imprecision",
 "confidence": 0.85, "feedback": "Presque ! Tu as bien vu que…"}
```

Modèle rapide (Sonnet 5, effort faible par défaut : `LUDIFUN_AI_EVALUATION_MODEL`), appel
journalisé dans `ai_runs` (étape `evaluation`) et soumis au plafond de coût journalier. Garde-fous :
seuls les points clés de la question sont retenus, score borné, retour de 400 caractères au plus,
confiance ≥ 0,4 ; la réponse de l'enfant est placée entre balises et traitée comme une donnée.

Si l'appel échoue, est écarté ou si le plafond est atteint : correction par les **mots clés** de
chaque point (deux tiers des mots importants présents), jamais bloquante pour l'enfant.

### 6.5 Plus tard

Assistant parent (V5) : réponses construites **uniquement** à partir des données agrégées du
tableau de bord, jamais du texte libre des leçons ; mode devoirs (V3) : dialogue guidé en
étapes à contrat fixe (« Qu'est-ce qu'on cherche ? »…), sans jamais produire la réponse finale.

---

## 7. API — nouvelles routes

| Méthode | Route | Rôle |
|---|---|---|
| POST | `/v1/lessons` (JSON `{text, grade?}`) | leçon depuis un texte (CDC §8.5) |
| GET · POST | `/v1/lessons/{id}/review` | passages incertains à vérifier ; réponses de l'enfant |
| POST | `/v1/sessions/{id}/items/{item_id}/help` | ✅ étape 14 : aide suivante (niveau 1 → 5) |
| POST | `/v1/sessions/{id}/extend` | activités supplémentaires (enfant rapide) |
| POST | `/v1/lessons/{id}/sessions` `{target_minutes?}` | séance à durée cible |
| GET | `/v1/children/{id}/skills` | ✅ étape 13 : compétences et notions de chaque leçon, niveau 0-5, couleur et explication |
| GET | `/v1/children/{id}/dashboard` | ✅ étape 14 : `error_types` et `recurring_errors` ajoutés (pas de route séparée) |
| GET · POST · DELETE | `/v1/children/{id}/goals[/{goal_id}]` | temps quotidien, contrôle, matière prioritaire |
| GET | `/v1/children/{id}/goals/{goal_id}/plan` | plan de révision jour par jour |
| GET | `/v1/me/plan` | l'enfant : séance du jour selon le plan (remplace la mission quand un contrôle approche) |

Réponse enrichie de `POST /v1/sessions/{id}/attempts` : `error_type`, `inserted_items`,
`engagement_hint`. Toutes les nouvelles routes suivent la séparation parent/enfant (V1 §16.1)
et ont leurs tests de séparation.

---

## 8. Écrans (CDC §77)

| CDC §77 | Existant | À faire |
|---|---|---|
| 1-4 Choix, connexion, création enfant, code/QR | ✅ | — |
| 5 Dashboard parent | ✅ ; compétences par leçon et « à renforcer » expliqué (étape 13) ; erreurs fréquentes (étape 14) | objectifs (étape 16) |
| 6 Dashboard enfant | ✅ mission du jour | plan du contrôle, durée du jour (étape 16) ; XP et série en V2 |
| 7-9 Ajouter une leçon, caméra, pages | ✅ | import de texte (étape 15) |
| 10-11 Analyse, leçon comprise | ✅ ; « Tu vas savoir : » et niveau de chaque notion en étoiles (étape 13) | « Peux-tu vérifier ? » (étape 15) |
| 12-16 Activité, réponse, correction, aide, suivante | ✅ ; « ❓ Je n'ai pas compris » et question ouverte (étape 14) | remédiation (étape 17) |
| 17 Résultat de séance | ✅ ; « ⬆️ Tu as progressé » : notions qui ont gagné un niveau (étape 13) | — |
| 18-19 Progression, historique | ✅ | compétences et erreurs (étapes 13, 14) |

---

## 9. Plan de développement

Suite du plan V1 (étapes 1 à 12 faites). Chaque étape : code + migration + tests +
documentation, intégration continue verte.

| # | Étape | Contenu | Terminé quand… |
|---|---|---|---|
| 13 ✅ | **Compétences et niveaux de compréhension** | migration 0003 (compétences, niveaux), analyse v2, maîtrise par niveau et par compétence, niveau affiché 0-5, statuts expliqués, écrans leçon, bilan et tableau de bord | une leçon réelle donne des compétences reliées aux notions ; 5 QCM réussis ne suffisent plus à « maîtrisé » (test) |
| 14 ✅ | **Aide, questions ouvertes, types d'erreurs** | matériel v2 (aides, distracteurs typés, questions ouvertes), évaluateur IA, bouton « Je n'ai pas compris », type d'erreur par réponse, erreurs récurrentes côté parent | parcours testé : aide 1 → 5 sans voir la réponse avant 5 ; réponse ouverte corrigée ; erreur récurrente signalée |
| 15 | **Import de texte et lecture vérifiée** | leçon depuis un texte collé, OCR v2 (passages incertains), écran « Peux-tu vérifier ? » | une photo avec un mot illisible demande une vérification avant l'analyse |
| 16 | **Objectifs du parent** | temps quotidien (séance à durée cible), contrôle à venir et plan jour par jour, matière prioritaire | un contrôle saisi vendredi donne un plan suivi par l'enfant et recalculé après chaque séance |
| 17 | **Adaptation en temps réel et engagement** | remédiation insérée après deux échecs, signaux de fatigue, extension de séance | séance simulée : deux échecs déclenchent la remédiation ; réponses au hasard proposent une pause |
| 18 | **Tests avec de vraies familles** (ancienne étape 13) | 30 leçons réelles, 5 enfants et parents, évaluation §17 V1 | critères de passage atteints |
| 19 | **Bêta Android** (ancienne étape 14) | hébergement UE, e-mails, documents RGPD, Play Store test fermé | 20 familles testeuses |

Versions suivantes (CDC §99-§104), dans l'ordre du CDC §110 :

- **V2 — ludique** : XP et série liés à l'effort, badges, missions narratives (§37), activités
  memory, classement, frise, association glisser-déposer, coloriage et carte (bibliothèque de
  gabarits d'images libres de droits : planètes, carte de France, squelette…) ;
- **V3 — moteur avancé** : difficulté dynamique fine, transfert, mode devoirs, référentiel des
  programmes (§105), profil d'apprentissage non figé (§82) ;
- **V4 — professeur IA** : oral (reconnaissance vocale, lecture audio), « Enseigne-moi », jeu de rôle ;
- **V5 — écosystème parent** : assistant parent, rapports hebdomadaires, notifications mesurées ;
- **V6 — iOS / iPadOS** : le code Flutter est déjà multiplateforme (dossier `ios/` généré) ;
  reste la signature, l'App Store et les tests sur appareils Apple.

---

## 10. Tests

- **Domaine** (sans base) : niveaux affichés, remédiation, fatigue, plans de contrôle — tables
  de cas, comme les tests actuels du composeur.
- **IA** : chaque contrat v2 a son jeu de réponses factices (`FakeProvider`) et ses cas
  invalides (compétence sans citation, question ouverte sans points clés…) ; l'évaluateur de
  réponses ouvertes est mesuré sur un corpus de réponses d'enfants annotées (étape 18).
- **API** : parcours complets par étape (comme `test_full_child_journey`) et séparation
  parent/enfant pour chaque nouvelle route.
- **Application** : tests de widgets par écran nouveau ; parcours enfant avec aide et
  remédiation ; parcours parent avec objectif et plan.
