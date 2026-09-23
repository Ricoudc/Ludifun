# Ludifun — Cahier des charges V1 (MVP 1)

> **Vision** : un coach de révision intelligent. L'enfant photographie sa leçon,
> l'IA comprend ce qu'il faut retenir, choisit comment le faire mémoriser,
> analyse les erreurs et adapte la séance suivante.

```
📸 JE PHOTOGRAPHIE → 🧠 L'IA COMPREND → 🎮 L'IA CHOISIT COMMENT ME FAIRE RÉVISER
→ 👦 JE JOUE / RÉPONDS → 📊 L'IA ANALYSE MES ERREURS → 🧠 ELLE ADAPTE LA SUITE → 🏆 JE PROGRESSE
```

---

## 1. Périmètre

### 1.1 Public
- Enfants du **CP à la 3e** (utilisation autonome dès le CE2, accompagnée avant).
- Matières : Français, Mathématiques, Histoire, Géographie, Sciences, Anglais… (l'IA détecte la matière).

### 1.2 Inclus dans la V1 (MVP 1)

| # | Fonctionnalité | Statut dans le dépôt |
|---|---|---|
| 1 | Profil enfant minimal (prénom/pseudo + classe) | ✅ API + écran |
| 2 | Photo d'1 à 6 pages (appareil ou galerie) | ✅ écran |
| 3 | Lecture de la photo (OCR) + compréhension IA | ✅ Claude vision, en un appel |
| 4 | Identification matière / niveau / sujet / notions | ✅ |
| 5 | Génération de la banque de questions | ✅ 6 formats |
| 6 | Modes : quiz rapide, entraînement, cartes mémoire, défi, points faibles | ✅ |
| 7 | Correction immédiate + explication | ✅ |
| 8 | Score et bilan par notion (acquis / à renforcer / à revoir) | ✅ |
| 9 | Mémorisation des erreurs, niveaux de maîtrise 0-5 | ✅ |
| 10 | Répétition espacée (J+1, J+2, J+4, J+7, J+14) | ✅ calcul, 🔜 notifications |
| 11 | Suppression des données (leçon, enfant) | ✅ |

### 1.3 Exclu de la V1 (versions suivantes)
- MVP 2 : XP, niveaux, badges, défis quotidiens, mini-jeux (memory, mot mystère, chronologie), notifications de rappel.
- MVP 3 : compte parent authentifié, plusieurs enfants par famille, statistiques détaillées.
- MVP 4 : mode oral (reconnaissance vocale, « professeur particulier »).
- Version iOS publiée (le code Flutter est déjà commun, seule la publication/les tests restent).

---

## 2. Écrans

Chaque écran indique : objectif, contenu, actions, états particuliers.

### É0 — Bienvenue (création du profil)
- **Objectif** : créer le profil enfant avec le minimum de données.
- **Contenu** : champ « prénom ou pseudo » (40 car. max), choix de la classe (CP → 3e).
- **Actions** : « C'est parti ! » → `POST /children`, l'identifiant est mémorisé localement.
- **États** : serveur injoignable → message d'erreur, on reste sur l'écran.

### É1 — Accueil
- **Contenu** : salutation, liste des leçons déjà photographiées (matière + titre), bouton flottant **📷 Nouvelle révision**, accès à la progression.
- **Actions** : ouvrir une leçon (É3), nouvelle révision (É2), progression (É6).
- **État vide** : « 📸 Photographie ta première leçon pour commencer ! ».

### É2 — Photographier la leçon
- **Contenu** : conseils de prise de vue, vignettes des pages prises (suppression possible), boutons *Galerie* / *Photographier* / *Ajouter une page*, bouton **Analyser ma leçon**.
- **Règles** : 6 pages max ; photo redimensionnée à 2000 px, qualité JPEG 85 côté téléphone.
- **Chargement** : « 🧠 Je lis ta leçon… » (10-40 s selon la longueur).
- **Erreurs** : photo illisible → « Je n'arrive pas à lire cette leçon. Essaie une photo plus nette. ».
- Amélioration d'image (perspective, contraste, recadrage) : 🔜 via un plugin de scan de document. Claude lit déjà correctement une photo légèrement penchée.

### É3 — « J'ai compris ta leçon » + choix du mode
- **Contenu** : Matière, Niveau, Sujet, résumé ; liste dépliable des notions (⭐ = essentielle).
- **Choix du mode** :

| Mode | Contenu | Taille |
|---|---|---|
| ⚡ Quiz rapide | QCM + vrai/faux | 10 |
| 🧠 Je m'entraîne | tous les formats | 10 |
| 🃏 Cartes mémoire | flashcards | 15 |
| 🏆 Défi | QCM, vrai/faux, texte à trous — 60 s | 10 |
| 🎯 Mes points faibles | notions de niveau < 4 uniquement | 8 |

### É4 — Question
- **En-tête** : « Question n / N », barre de progression, chrono (mode défi).
- **Formats** :
  - QCM / vrai-faux : boutons de réponse.
  - Texte à trous : champ texte (accents et petites fautes de frappe tolérés).
  - Carte mémoire : l'enfant retourne la carte puis indique « Je savais » / « Je ne savais pas ».
  - Association : une liste déroulante par élément de gauche.
  - Question ouverte (« Explique-moi ») : champ multiligne, corrigé par l'IA.
- **Après réponse** : carte ✅/🤔, explication, bonne réponse si erreur, éléments oubliés (question ouverte), bouton *Question suivante*.
- **Fin du chrono** : la séance est clôturée automatiquement.

### É5 — Bilan
- Message adapté au score (🎉 ≥ 8, 👍 ≥ 5, 💪 sinon), note sur 10, nombre de bonnes réponses.
- Liste des notions travaillées, triées de la plus fragile à la plus solide : 🟢 acquis (≥ 80 %), 🟠 à renforcer (50-79 %), 🔴 à revoir (< 50 %).
- Actions : *Retour à la leçon* (pour relancer un mode, typiquement « Mes points faibles »).

### É6 — Progression
- Minutes de révision sur 7 jours, nombre de leçons, taux de réussite global.
- Réussite par matière (🟢/🟠/🔴).
- **À réviser aujourd'hui** (notions dont la date de rappel est passée) et **À renforcer** (niveau ≤ 3) : un clic ouvre la leçon correspondante.
- Aucune comparaison entre enfants.

---

## 3. Architecture

```
Flutter (Android, puis iOS)
        │  HTTPS / JSON + multipart
        ▼
FastAPI  ──►  Pipeline IA (Claude)
  │            ├─ IA 1+2 : vision + analyse pédagogique  → LessonAnalysis
  │            ├─ IA 3   : génération des exercices        → QuestionBank
  │            └─ IA 4   : correction des réponses libres  → OpenAnswerEvaluation
  │
  ├─ Moteur pédagogique (règles, sans IA, testé unitairement)
  │    ├─ evaluator : correction QCM / trous / association / flashcards
  │    ├─ mastery   : niveaux 0-5 + répétition espacée
  │    └─ planner   : IA 5 « quoi réviser maintenant ? »
  ▼
PostgreSQL (SQLite en développement)
```

Choix structurants :
- **OCR + compréhension en un seul appel** : Claude lit directement la photo. Pas de moteur OCR séparé à maintenir, meilleure robustesse sur l'écriture manuscrite et les mises en page de manuels.
- **Sorties structurées** : chaque appel IA renvoie un JSON validé par un schéma Pydantic (`backend/app/ai/schemas.py`). Les questions mal formées sont écartées avant enregistrement.
- **Banque de questions générée une fois** à l'analyse de la leçon (≈ 4 questions × notion, difficultés 1 à 4) : les séances démarrent instantanément et ne coûtent rien en IA, sauf pour les questions ouvertes.
- **Moteur hors-ligne (`FakeLLM`)** : l'API fonctionne sans clé pour développer l'application et lancer les tests.
- **Repli automatique** : si le modèle décline une requête, l'API relance sur un modèle de repli (`fallbacks: "default"`).

---

## 4. Modèle de données

| Table | Champs principaux | Rôle |
|---|---|---|
| `child` | id, display_name, grade, created_at | Profil minimal |
| `lesson` | id, child_id, subject, grade, title, summary, source_text | Leçon analysée (texte seulement, **jamais la photo**) |
| `notion` | id, lesson_id, label, kind, content, importance | Ce qu'il faut retenir |
| `question` | id, lesson_id, notion_id, kind, difficulty, prompt, choices, answer, explanation, pairs | Banque d'exercices |
| `revisionsession` | id, child_id, lesson_id, mode, question_ids, time_limit_s, started_at, finished_at | Une séance |
| `answer` | id, session_id, question_id, notion_id, given, score, correct, time_ms | Chaque réponse (analyse des erreurs) |
| `notionmastery` | id, child_id, notion_id, level, next_review_at, last_reviewed_at | Maîtrise + prochain rappel |

Types de notion : `date, vocabulaire, definition, personnage, evenement, lieu, regle, formule, calcul, concept`.
Types de question : `qcm, vrai_faux, texte_a_trous, flashcard, association, question_ouverte`.
Difficultés : 1 reconnaître · 2 se rappeler · 3 relier/appliquer · 4 expliquer.

Tables prévues pour les versions suivantes : `parent`, `family`, `badge`, `xp_event`, `daily_challenge`, `voice_answer`.

---

## 5. API REST (V1)

Documentation interactive : `http://localhost:8000/docs`.

| Méthode | Route | Description |
|---|---|---|
| POST | `/children` | Créer un profil `{display_name, grade}` |
| GET | `/children/{id}` | Lire un profil |
| DELETE | `/children/{id}` | **Effacement** de l'enfant et de toutes ses données |
| GET | `/children/{id}/lessons` | Leçons de l'enfant |
| GET | `/children/{id}/progress` | Tableau de bord (réussite, matières, à renforcer, rappels dus) |
| POST | `/lessons` | *multipart* : `child_id`, `images[]` (1-6, JPEG/PNG/WebP, 10 Mo max) et/ou `text` → leçon analysée |
| GET | `/lessons/{id}` | Leçon + notions |
| DELETE | `/lessons/{id}` | Supprimer une leçon et son historique |
| POST | `/lessons/{id}/sessions` | Démarrer une séance `{mode}` → questions **sans les réponses** |
| POST | `/sessions/{id}/answers` | `{question_id, answer, time_ms}` → correction + explication |
| POST | `/sessions/{id}/finish` | Clôturer → bilan + mise à jour de la maîtrise |

Codes d'erreur : 404 ressource absente · 409 séance close / question déjà répondue · 413 photo trop lourde · 415 format non supporté · 422 entrée invalide ou leçon illisible · 502 IA indisponible.

---

## 6. Moteur pédagogique

### 6.1 Choix de l'activité selon le contenu (prompt IA 3)

| Contenu | Activités privilégiées |
|---|---|
| Date | QCM, vrai/faux, année à compléter |
| Vocabulaire, définition | Cartes mémoire, QCM, texte à trous |
| Personnage | « Qui suis-je ? » (QCM), association |
| Événement, lieu | QCM, association, vrai/faux |
| Règle, formule, calcul | QCM, texte à trous avec exemple |
| Concept | Question ouverte, vrai/faux |

### 6.2 Correction
- QCM / vrai-faux : comparaison exacte (casse et accents ignorés).
- Texte à trous : similarité ≥ 85 % (« revolusion » accepté pour « Révolution »).
- Association : score = paires correctes / paires totales.
- Carte mémoire : auto-évaluation.
- Question ouverte : IA 4, score 0-1 sur le fond (pas l'orthographe), liste des oublis.
- Réponse « juste » si score ≥ 0,6.

### 6.3 Maîtrise et répétition espacée
À la fin de chaque séance, pour chaque notion travaillée (taux de réussite *r*) :

| Niveau actuel | r ≥ 80 % | 50 % ≤ r < 80 % | r < 50 % |
|---|---|---|---|
| 0 (jamais vue) | 3 | 2 | 1 |
| 1 à 5 | +1 (max 5) | inchangé | −1 (min 1) |

Prochain rappel : niveau 1 → J+1 · 2 → J+2 · 3 → J+4 · 4 → J+7 · 5 → J+14.

### 6.4 Sélection des questions (IA 5, règles)
1. Priorité de chaque notion = (6 − niveau) × poids d'importance (essentielle 3, importante 2, complémentaire 1).
2. Difficulté ciblée selon le niveau : 0-1 → 1-2 · 2 → 1-3 · 3 → 2-3 · 4-5 → 3-4.
3. Tirage en tours successifs : une question par notion et par tour, notions prioritaires d'abord → la séance couvre largement la leçon tout en insistant sur les points faibles.
4. Mode « Mes points faibles » : seulement les notions de niveau < 4.

---

## 7. Prompts IA

Les prompts complets sont dans `backend/app/ai/prompts.py` (versionnés avec le code) :

| Prompt | Rôle | Effort |
|---|---|---|
| `ANALYSIS_SYSTEM` | Retranscrire, identifier matière/niveau, extraire 3-12 notions typées et hiérarchisées, ne rien inventer, signaler une photo illisible | élevé |
| `GENERATION_SYSTEM` | Choisir le format selon le type de notion, difficultés 1→4, règles de forme par format, ton bienveillant | moyen |
| `EVALUATION_SYSTEM` | Corriger une réponse libre sur le fond, retour encourageant, oublis | faible |

Les prompts système sont fixes (mis en cache) ; le contenu de la leçon est toujours passé dans le message utilisateur, entre balises `<lecon>`.

---

## 8. Protection des données (enfants, RGPD)

Intégré dès la conception :
- **Minimisation** : prénom ou pseudo + classe. Ni nom, ni date de naissance, ni e-mail enfant.
- **Photos non conservées** : lues en mémoire, transmises à l'IA, jamais écrites sur disque. Seul le texte de la leçon est stocké.
- **Droit à l'effacement** : `DELETE /children/{id}` supprime tout (leçons, questions, réponses, maîtrise).
- **Pas de publicité**, pas de classement entre enfants.
- **À faire avant bêta publique** : compte parent + consentement parental (enfants < 15 ans en France), authentification des appels API, chiffrement TLS obligatoire, hébergement UE, durée de conservation (ex. suppression auto après 12 mois d'inactivité), politique de confidentialité, registre des traitements, contrat de sous-traitance avec le fournisseur d'IA, analyse d'impact (AIPD).

---

## 9. Critères d'acceptation V1

1. Une photo nette d'une page de manuel de CM1 produit en moins de 45 s une leçon avec la bonne matière et au moins 3 notions pertinentes.
2. Aucune question générée ne porte sur une information absente de la leçon (revue manuelle sur 20 leçons tests).
3. Une séance de 10 questions se joue sans temps d'attente entre les questions fermées.
4. Une notion ratée en séance 1 apparaît en priorité en séance 2 (« Mes points faibles »).
5. La suppression d'un enfant ne laisse aucune donnée associée en base.
6. Les tests automatiques du backend passent (`pytest`).

---

## 10. Suite de la feuille de route

| Étape | Contenu |
|---|---|
| MVP 1 (ce dépôt) | Photo → analyse → 6 formats d'exercices → correction → bilan → maîtrise |
| 1.1 | Scan de document (perspective/contraste), notifications de rappel, jeu de 20 leçons tests pour évaluer la qualité de l'IA |
| MVP 2 | XP, niveaux, badges, mission « sauver le royaume », memory, mot mystère, chronologie, défi quotidien |
| MVP 3 | Compte parent, plusieurs enfants, historique, recommandations |
| MVP 4 | Mode oral : questions et réponses à voix haute, « professeur particulier » |
| Bêta Android | Play Store (test fermé), conformité RGPD complète |
| iOS | Même code Flutter : permissions caméra, tests iPad, App Store |
