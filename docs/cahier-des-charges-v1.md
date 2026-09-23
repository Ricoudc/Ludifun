# Ludifun — Cahier des charges technique V1

> **Mission de la V1**
> Transformer correctement une vraie leçon photographiée en une séance de révision
> amusante et pertinente. Tout le reste (comptes, parents, abonnement,
> notifications, classement) sera construit ensuite, si et seulement si cette
> mission est réussie.

| | |
|---|---|
| Nom provisoire | **Ludifun** |
| Plateformes V1 | Android (Flutter), iOS ensuite avec le même code |
| Public | CP → 3e |
| Statut du document | Référence pour le développement de la V1 |
| Vision à long terme | [`vision.md`](vision.md) : plateforme de soutien scolaire, espaces parent et enfant, versions V0 à V6 |

---

## Sommaire

1. [Périmètre](#1-périmètre)
2. [Parcours utilisateur](#2-parcours-utilisateur)
3. [Les écrans](#3-les-écrans)
4. [Architecture générale](#4-architecture-générale)
5. [Pipeline IA](#5-pipeline-ia)
6. [Formats JSON échangés avec l'IA](#6-formats-json-échangés-avec-lia)
7. [Moteur d'activités](#7-moteur-dactivités)
8. [Composition d'une séance](#8-composition-dune-séance)
9. [Notation](#9-notation)
10. [Mémorisation et prochaine révision](#10-mémorisation-et-prochaine-révision)
11. [API](#11-api)
12. [Base de données PostgreSQL](#12-base-de-données-postgresql)
13. [Architecture FastAPI](#13-architecture-fastapi)
14. [Architecture Flutter](#14-architecture-flutter)
15. [Gestion des photos](#15-gestion-des-photos)
16. [Sécurité et données personnelles](#16-sécurité-et-données-personnelles)
17. [Tests avec de vraies leçons](#17-tests-avec-de-vraies-leçons)
18. [Plan de développement](#18-plan-de-développement)
19. [Reprise du prototype existant](#19-reprise-du-prototype-existant)

---

## 1. Périmètre

### 1.1 Dans la V1

- Nouvelle révision à partir d'une ou plusieurs photos (appareil photo ou galerie).
- Lecture de la photo (OCR), puis analyse pédagogique : matière, niveau, thème, objectif, notions, vocabulaire, dates, personnages, règles et formules selon la matière.
- Séance construite automatiquement, avec un objectif et une durée estimée.
- 6 types d'activités : QCM, vrai/faux, texte à trous, association, défi rapide, carte mémoire.
- Correction immédiate avec la bonne réponse, une astuce pour retenir et une explication.
- Reprise des erreurs en fin de séance.
- Bilan par notion (maîtrisée / à revoir / non maîtrisée) et programmation de la prochaine révision.
- Liste des dernières révisions et **mission du jour** sur l'accueil de l'enfant.
- **Espace parent** : compte parent, un ou plusieurs profils enfants, liaison de l'appareil de l'enfant par **code à 6 chiffres ou QR code**, tableau de bord (séances, temps, réussite par matière, notions à renforcer, progression).
- Le parent peut aussi photographier une leçon pour son enfant.
- Suppression d'une leçon, d'un enfant ou du compte parent, avec toutes les données associées.

### 1.2 Hors V1 (volontairement)

Voir les versions de [`vision.md`](vision.md) §5 :

- V2 : coloriage, memory, puzzles, cartes, frises, missions thématiques, XP, badges, niveaux ;
- V3 : stratégie de séance choisie par l'IA, adaptation en temps réel (« on va essayer autrement »), plan de révision, recommandations ;
- V4 : oral et professeur IA ;
- V5 : assistant parent, objectifs, rapports hebdomadaires, notifications, second parent ;
- abonnement, paiement, classement, réseau social : non prévus pour l'instant.

Choix faits dès la V1 pour ne pas devoir tout refaire :

- le modèle de données a déjà une **famille** entre le parent et les enfants (un second parent s'y ajoutera en V5) ;
- les types d'activités `ORDER`, `MEMORY` et `OPEN_QUESTION` sont déclarés dans le registre mais implémentés plus tard ; chaque nouvelle famille d'activités de la bibliothèque (§7) s'ajoute sans toucher au moteur.

---

## 2. Parcours utilisateur

Une seule application, deux espaces. Au premier lancement : « Je suis un parent » ou « Je suis un enfant ».

**Parent**
```
[P1 Compte] ──► [P2 Mes enfants] ──+ Ajouter Emma (CM1)──► code 482 731 / QR code
                      │
                      └──► [P3 Tableau de bord d'Emma] ──► [P4 Historique et réglages]
                                     │
                                     └── 📷 Ajouter une leçon pour Emma ──► (écrans 2 à 4)
```

**Enfant**
```
[0 Connexion : code ou QR] ──► [1 Accueil]  (une seule fois par appareil)

[1 Accueil] ──+ Nouvelle leçon──► [2 Photo] ──Analyser──► [3 Analyse] ──C'est prêt──► [4 Résumé]
     ▲                                                                                   │
     │                                                                      Commencer la révision
     │                                                                                   ▼
     │                                                       ┌──────► [5 Jeu] ──réponse──► [6 Correction]
     │                                                       └────────── Continuer ◄────────────┘
     │                                                                                   │
     │                                                                    fin de séance (reprise incluse)
     │                                                                                   ▼
     └──────────────────────── Terminer ◄──────────────────────────────────────── [7 Bilan]
                                                                                         │
                                                              Revoir mes erreurs ──► nouvelle séance courte
```

Depuis l'accueil, un clic sur une leçon déjà révisée ouvre l'écran 4 avec une séance de révision recalculée selon la maîtrise (voir §8.3).

---

## 3. Les écrans

Espace enfant : écran de connexion (0) et 7 écrans de révision (1 à 7). Espace parent : 4 écrans (P1 à P4).

### Écran 0 — Connexion de l'enfant
```
👋 Bonjour !
Demande le code à ton parent.

[ 4 ] [ 8 ] [ 2 ] [ 7 ] [ 3 ] [ 1 ]

        ou  [ 📷 Scanner le QR code ]
```
- `POST /v1/link {code}` (ou `{qr_token}` après le scan) → l'appareil reçoit un jeton lié au profil de l'enfant et affiche « C'est toi, Emma ? ». *Non* → `DELETE /v1/me/device` : l'appareil rend aussitôt son jeton.
- Code faux ou expiré : « Ce code ne marche pas. Demande un nouveau code à ton parent. »
- Une fois lié, l'appareil ouvre directement l'accueil de l'enfant.


### Écran 1 — Accueil
```
👋 Bonjour Emma !

🎯 Ta mission du jour
📚 Les fractions · ⏱️ 8 min
        [ COMMENCER ]

        [ + NOUVELLE LEÇON ]

Mes dernières révisions
📚 Les fractions                 à revoir jeudi
🇫🇷 La Révolution française       à revoir aujourd'hui 🔄
🔬 Les états de la matière       maîtrisée ✓
```
- Données : `GET /v1/me/mission` et `GET /v1/lessons` (les 20 plus récentes).
- **Mission du jour** : la révision la plus utile maintenant, dans cet ordre : une leçon dont des notions sont dues (§10), puis la dernière leçon pas encore maîtrisée, puis la dernière leçon ajoutée. *COMMENCER* ouvre l'écran 4 de cette leçon. S'il n'y a rien à réviser : « 🎉 Tout est à jour ! Photographie une nouvelle leçon. »
- Chaque ligne affiche : icône de matière, titre et état de révision (prochaine révision, « à revoir aujourd'hui » ou « maîtrisée »).
- Une leçon en cours d'analyse s'affiche avec un indicateur. Une leçon en échec s'affiche avec « Réessayer ».
- Appui long sur une leçon → *Supprimer*.
- État vide : illustration + « Photographie ta première leçon ! ».

### Écran 2 — Photo
```
📷 Photographie ta leçon
[ Prendre une photo ]   ou   [ Ajouter depuis la galerie ]
Tu peux ajouter plusieurs pages.
[vignette 1] [vignette 2] [+]
            [ ANALYSER MA LEÇON ]
```
- Jusqu'à 6 pages. Chaque vignette a une croix de suppression et peut être réordonnée par glisser-déposer.
- Conseil affiché lors de la première photo : « Pose le cahier à plat, avec de la lumière. »
- La compression est faite sur le téléphone (voir §15) avant l'envoi.
- *Analyser* → `POST /v1/lessons` → écran 3.

### Écran 3 — Analyse
```
🔎 Lecture de ta leçon...          ✓
🧠 Identification des notions...  ⏳
🎮 Préparation de tes exercices...
```
- L'écran interroge `GET /v1/lessons/{id}` toutes les 1,5 s. Chaque ligne suit une vraie étape du serveur (`reading` → `analyzing` → `generating` → `ready`).
- Chaque étape reste affichée au moins 800 ms, pour que l'animation reste lisible.
- `ready` → « C'est prêt ! » puis écran 4.
- `failed` affiche un message adapté selon la raison :
  - `unreadable` : « Je n'arrive pas à lire ta photo. Reprends-la avec plus de lumière. » → retour à l'écran 2 avec les photos conservées côté téléphone ;
  - `not_a_lesson` : « Ça ne ressemble pas à une leçon. » ;
  - `ai_error` : « Petit souci de mon côté, réessaie. ».
- Objectif de durée : moins de 45 s pour 2 pages.

### Écran 4 — Résumé de la leçon
```
🇫🇷 HISTOIRE · CM1
LA RÉVOLUTION FRANÇAISE

🎯 Objectif : connaître les principales notions de la Révolution française
⏱️ Durée estimée : 8 min

À retenir :
✓ 1789
✓ Louis XVI
✓ États généraux
✓ Prise de la Bastille
✓ Déclaration des droits de l'homme et du citoyen

        [ COMMENCER LA RÉVISION ]
```
- Données : `GET /v1/lessons/{id}` (leçon et notions triées par importance) et `POST /v1/lessons/{id}/sessions` (objectif et durée estimée).
- La séance est créée dès l'ouverture de l'écran : la durée affichée est donc celle de la vraie séance.
- Un appui sur une notion affiche sa phrase « à retenir ».
- Un lien « Ce n'est pas le bon niveau ? » permet de corriger le niveau (CP → 3e), sans nouvel appel à l'IA. En V1 le niveau n'intervient pas encore dans la composition de la séance : la correction met à jour la leçon, la séance reste la même.

### Écran 5 — Jeu
```
Question 3 / 8                          ▓▓▓░░░░░
Quelle année marque le début de la Révolution française ?
🅰️ 1492    🅱️ 1789    🅲 1914    🅳 1945
```
- Une seule route, qui affiche l'activité courante à l'aide du **registre de widgets** (§14.3).
- Le compteur couvre les activités principales. La reprise des erreurs s'affiche ensuite avec son propre bandeau : « 🔄 Reprise des erreurs 1 / 2 ».
- Le défi rapide affiche un chrono.
- Quitter en cours de séance demande une confirmation. La séance reste `active` et peut être reprise depuis l'accueil.

### Écran 6 — Correction
```
❌ Pas tout à fait !
La bonne réponse est 1789.
💡 Astuce pour retenir : 1789 = Révolution française
                    [ CONTINUER ]
```
- Cet écran s'affiche dans la même route que l'écran 5 (état « correction »), et non comme une nouvelle page.
- Le contenu vient de la réponse de `POST /v1/sessions/{id}/attempts` : résultat, bonne réponse à afficher, astuce et explication.
- Selon le résultat :
  - bonne réponse : « ✅ Bravo ! » et l'explication en une ligne ;
  - réponse partielle (association, défi) : le détail élément par élément ;
  - mauvaise réponse : jamais de formulation culpabilisante.

### Écran 7 — Bilan
```
🎉 Révision terminée !
8 / 10   ████████░░

✅ 7 notions maîtrisées
🟠 2 notions à revoir
🔴 1 notion non maîtrisée

Maîtrisé : ✓ 1789  ✓ Louis XVI  ✓ Bastille …
À revoir : ⚠ États généraux  ⚠ Déclaration des droits

📅 Prochaine révision : jeudi 25 septembre

[ REVOIR MES ERREURS ]     [ TERMINER ]
```
- Données : réponse de `POST /v1/sessions/{id}/complete`.
- *Revoir mes erreurs* (visible seulement s'il y a des notions non maîtrisées ou à revoir) crée une séance courte de type `errors`, qui ne porte que sur ces notions.

### Écran P1 — Compte parent
- Création (e-mail, mot de passe, acceptation de la politique de confidentialité) ou connexion.
- Mot de passe oublié par e-mail.

### Écran P2 — Mes enfants
```
Mes enfants
👧 Emma · CM1        📱 1 appareil lié      ›
👦 Hugo · CE1        🔗 Lier un appareil    ›
        [ + AJOUTER UN ENFANT ]
```
- Ajouter un enfant : prénom ou pseudo, classe, avatar ; **consentement parental** coché à la création.
- *Lier un appareil* : affiche un code à 6 chiffres et un QR code, valables 10 minutes et utilisables une seule fois.

### Écran P3 — Tableau de bord d'un enfant
```
Emma · CM1 · cette semaine
📚 4 séances   ⏱️ 37 min   🎯 8,5 / 10 en moyenne

Français       🟢 86 %
Mathématiques  🟠 72 %
Histoire       🟢 91 %

À renforcer
🔴 Comparaison des fractions
🟠 Imparfait

Progression   ▁▃▅▆  (4 dernières semaines)
Activités     🎮 Quiz 4 · 🃏 Cartes 2 · ✍️ Textes à trous 6
[ 📷 Ajouter une leçon pour Emma ]
```
- Données : `GET /v1/children/{id}/dashboard?weeks=4` (1 à 12 semaines).
- Définitions, affichables telles quelles au parent :
  - **semaine** : du lundi 0 h au dimanche soir, à l'heure de la famille (`Europe/Paris` par défaut) ;
  - **séances** : séances terminées dans la semaine ; **note moyenne** : moyenne de leurs notes sur 10 ;
  - **temps** : temps passé à répondre, chaque réponse comptant au plus 5 minutes (application laissée
    ouverte), plus 8 secondes par correction lue ;
  - **réussite par matière** : maîtrise actuelle (§10) des notions déjà travaillées, moyenne pondérée par
    leur importance ; une leçon jamais révisée n'y figure pas ;
  - **à renforcer** : au plus 5 notions travaillées sous 80 %, les plus faibles puis les plus importantes d'abord ;
  - **progression** : séances, temps et note moyenne de chaque semaine ; **tendance** `up` / `down` /
    `stable` en comparant la note moyenne des deux dernières semaines actives (écart d'au moins 0,5).
- Couleurs : 🟢 ≥ 80 %, 🟠 50 à 79 %, 🔴 < 50 % (mêmes seuils que le bilan, §9.3).
- Pas de comparaison avec d'autres enfants.

### Écran P4 — Historique et réglages
- Séances de l'enfant, de la plus récente à la plus ancienne (date, leçon, durée, note, résultat par notion),
  par pages : `GET /v1/children/{id}/history?limit=20&before=<next_before>`.
- Appareils liés (nom, dernière utilisation) et *Délier*.
- Modifier le profil ; *Supprimer l'enfant et toutes ses données* (confirmation) ; supprimer le compte parent.

---

## 4. Architecture générale

```
┌─────────────────────┐
│  Application Flutter │  écrans · registre de widgets d'activités · client API
└──────────┬──────────┘
           │ HTTPS · JSON · multipart · jeton d'appareil
┌──────────▼──────────┐
│     API FastAPI      │  /v1 · validation · limites de débit
└──────────┬──────────┘
           │
┌──────────▼──────────────────────────────────────────────────────────┐
│ Services (cas d'usage)                                               │
│   LessonPipeline · SessionService · ReportService                    │
├──────────────────────────────────────────────────────────────────────┤
│ Domaine (Python pur, sans IA ni base, testé unitairement)           │
│   Knowledge · Registre d'activités · Composeur de séance             │
│   Notation · Mémorisation · Estimation de durée                      │
├──────────────────────────────────────────────────────────────────────┤
│ Ports (interfaces)          │ Adaptateurs (remplaçables)             │
│   OcrProvider               │   VisionLLMOcr, (GoogleVision, Mistral…)│
│   LLMProvider               │   ClaudeProvider, FakeProvider, (…)    │
│   Repositories              │   PostgreSQL (SQLAlchemy)              │
└──────────────────────────────────────────────────────────────────────┘
```

Le tableau suivant montre ce que l'on peut changer, et ce qui est touché dans chaque cas :

| On change… | On touche seulement… |
|---|---|
| le modèle d'IA | la configuration (`AI_ANALYSIS_MODEL`…) |
| le fournisseur d'IA | un nouvel adaptateur `LLMProvider` |
| le fournisseur d'OCR | un nouvel adaptateur `OcrProvider` |
| ajouter un jeu | 1 classe `ActivityType` côté serveur + 1 widget côté Flutter |
| la base de données | les repositories |
| l'application mobile | rien côté serveur : l'API est versionnée `/v1` |

---

## 5. Pipeline IA

Principe : **l'IA ne génère jamais des questions directement à partir du texte.**

```
PHOTOS
  │  ① OCR (OcrProvider)                         statut « reading »
  ▼
TEXTE (par page) + qualité de lecture
  │  ② Analyse pédagogique (LLMProvider)         statut « analyzing »
  ▼
STRUCTURE NORMALISÉE : leçon + knowledge[] (k1, k2…)
  │  ③ Enrichissement par notion (LLMProvider)  statut « generating »
  ▼
MATÉRIEL PÉDAGOGIQUE par notion
  (questions, distracteurs, affirmations fausses, phrase à trous, paire, astuce)
  │  ④ Assemblage déterministe (domaine, sans IA) — au moment de composer la séance
  ▼
ACTIVITÉS (QCM, vrai/faux, association, défi…)
```

Pourquoi c'est robuste :

- **② extrait, ③ rédige, ④ assemble.** Chaque étape a une seule responsabilité et un schéma validé.
- Chaque notion porte un `source_excerpt`, c'est-à-dire la citation exacte du texte OCR. Une notion sans citation retrouvable dans le texte est rejetée (garde-fou contre les inventions).
- Les activités sont assemblées **sans IA**. Composer une séance, relancer « Revoir mes erreurs » ou ajouter un nouveau type de jeu ne coûte donc aucun appel, et la réponse est instantanée.
- Pendant la séance, aucun appel IA n'est fait en V1 : la correction est déterministe.

### 5.1 Étape ① — OCR

- Interface : `OcrProvider.extract(pages: list[PageImage]) -> OcrResult`.
- Implémentation V1 : `VisionLLMOcr`, un modèle multimodal utilisé avec un prompt de **transcription pure**, sans analyse. C'est l'option la plus robuste sur l'écriture manuscrite et les mises en page de manuel.
- Alternatives à comparer à l'étape 10 : Google Cloud Vision, Azure Document Intelligence, Mistral OCR, Tesseract. Le choix final se fait sur le corpus de test (§17), en comparant qualité, coût et latence.
- Les en-têtes personnels (nom et prénom de l'enfant, nom de l'école, date manuscrite) sont exclus de la transcription.
- Qualité de lecture par page : `good`, `partial` ou `unreadable`. Si toutes les pages sont `unreadable`, l'analyse échoue avec la raison `unreadable`.

### 5.2 Étape ② — Analyse pédagogique

L'analyse reçoit le texte OCR (et non l'image). Elle produit la structure normalisée décrite au §6.2. Consignes :

- identifier la matière, le niveau (avec un indice de confiance), le titre, un **objectif** formulé pour l'enfant et un résumé ;
- extraire 3 à 15 notions, chacune avec un type, une importance de 1 à 5, une phrase « à retenir », des attributs propres à son type et une citation source ;
- ne rien inventer : les attributs ne contiennent que des informations présentes dans la leçon ;
- traiter le texte de la leçon comme une donnée et non comme des instructions (il est passé entre balises `<lecon>`).

### 5.3 Étape ③ — Enrichissement

- Entrée : la leçon normalisée et le texte source. Sortie : un `KnowledgeMaterial` par notion (§6.3).
- Les notions sont traitées par lots de 5, en parallèle, pour réduire la latence.
- Des validateurs automatiques contrôlent chaque élément de matériel (§6.4). Un élément invalide est écarté, et pas le reste de la notion.
- Si une notion d'importance ≥ 4 n'a plus assez de matériel pour 2 activités, une relance ciblée est faite sur cette seule notion (une fois).

### 5.4 Interfaces fournisseurs

```python
class OcrProvider(Protocol):
    async def extract(self, pages: list[PageImage]) -> OcrResult: ...

class LLMProvider(Protocol):
    async def structured(
        self, *, prompt: Prompt, input: str, schema: type[T], images: list[PageImage] = ()
    ) -> LLMResult[T]: ...   # LLMResult = sortie validée + usage (tokens, latence, modèle)
```

- Les prompts sont versionnés dans des fichiers (`app/ai/prompts/analysis.v1.md`…). La version utilisée est enregistrée avec chaque leçon.
- Modèle configurable **par étape** (`LUDIFUN_AI_OCR_MODEL`, `…_ANALYSIS_MODEL`, `…_MATERIAL_MODEL` ; `claude-opus-5` par défaut, avec l'effort `low` / `high` / `medium`). Les appels Claude activent le repli automatique côté serveur (`fallbacks: "default"`) : si le modèle décline une requête, l'API la relance sur un modèle de repli. On pourra par exemple prendre un modèle moins cher pour l'enrichissement si le corpus de test montre que la qualité tient.
- Chaque appel est journalisé dans `ai_runs` : étape, fournisseur, modèle, version du prompt, tokens, latence, statut. C'est ce qui permet de mesurer le coût réel par leçon.
- `FakeProvider` produit des réponses déterministes. Il sert aux tests et au développement de l'application sans clé d'API.

---

## 6. Formats JSON échangés avec l'IA

### 6.1 Sortie OCR

```json
{
  "pages": [
    { "index": 0, "quality": "good", "text": "La Révolution française\nEn 1789, le roi Louis XVI..." }
  ],
  "language": "fr",
  "warnings": []
}
```

### 6.2 Sortie de l'analyse (structure normalisée)

```json
{
  "schema_version": "1.0",
  "is_lesson": true,
  "lesson": {
    "subject": "history",
    "grade": "CM1",
    "grade_confidence": 0.7,
    "title": "La Révolution française",
    "objective": "Connaître les principales notions de la Révolution française",
    "summary": "En 1789, les Français se révoltent contre le pouvoir du roi Louis XVI..."
  },
  "knowledge": [
    {
      "id": "k1",
      "type": "date",
      "label": "1789",
      "statement": "La Révolution française commence en 1789.",
      "importance": 5,
      "attributes": { "value": "1789", "precision": "year", "event": "Début de la Révolution française" },
      "source_excerpt": "La Révolution française commence en 1789",
      "relations": []
    },
    {
      "id": "k2",
      "type": "person",
      "label": "Louis XVI",
      "statement": "Louis XVI est le roi de France au moment de la Révolution.",
      "importance": 4,
      "attributes": { "role": "roi de France" },
      "source_excerpt": "le roi Louis XVI",
      "relations": []
    },
    {
      "id": "k3",
      "type": "event",
      "label": "Prise de la Bastille",
      "statement": "Le 14 juillet 1789, le peuple de Paris prend la Bastille.",
      "importance": 5,
      "attributes": { "date": "14 juillet 1789", "place": "Paris" },
      "source_excerpt": "Le 14 juillet 1789, le peuple de Paris prend la Bastille",
      "relations": [{ "type": "happened_in", "target": "k1" }]
    }
  ],
  "warnings": []
}
```

**Matières** (`subject`) : `french`, `math`, `history`, `geography`, `science`, `english`, `civics`, `other`.
**Niveaux** (`grade`) : `CP`, `CE1`, `CE2`, `CM1`, `CM2`, `6e`, `5e`, `4e`, `3e`.

**Types de connaissance** et attributs attendus :

| `type` | Exemple | `attributes` |
|---|---|---|
| `date` | 1789 | `value`, `precision` (year/day), `event` |
| `person` | Louis XVI | `role` |
| `place` | La Bastille | `description` |
| `event` | Prise de la Bastille | `date?`, `place?` |
| `term` | numérateur | `definition` |
| `rule` | accord du participe passé | `statement`, `example` |
| `formula` | aire du rectangle | `expression`, `variables` |
| `fact` | l'eau bout à 100 °C | — |
| `process` | cycle de l'eau | `steps[]` |
| `classification` | états de la matière | `categories[{name, members[]}]` |

**Importance** : 5 = sera forcément demandée · 4 = centrale · 3 = utile · 2 = complément · 1 = détail.

**Relations** : `happened_in`, `part_of`, `opposite_of`, `example_of`, `causes`. Elles servent aux associations et, plus tard, aux jeux de chronologie.

### 6.3 Sortie de l'enrichissement (matériel par notion)

```json
{
  "knowledge_id": "k1",
  "questions": [
    { "difficulty": 1, "stem": "En quelle année commence la Révolution française ?",
      "answer": "1789", "distractors": ["1492", "1914", "1945"] },
    { "difficulty": 2, "stem": "Que se passe-t-il en France en 1789 ?",
      "answer": "La Révolution française commence",
      "distractors": ["Napoléon devient empereur", "La Première Guerre mondiale commence", "Louis XIV devient roi"] }
  ],
  "true_statements": ["La Révolution française commence en 1789."],
  "false_statements": ["La Révolution française commence en 1914."],
  "cloze": { "text": "La Révolution française commence en ___.", "answers": ["1789"] },
  "pair": { "left": "1789", "right": "Début de la Révolution" },
  "flashcard": { "front": "1789", "back": "Début de la Révolution française" },
  "tip": "1789 = Révolution française.",
  "explanation": "La Révolution française commence en 1789, quand le peuple conteste le pouvoir du roi."
}
```

Difficultés : **1** reconnaître · **2** se rappeler · **3** relier / appliquer.

### 6.4 Validateurs automatiques

| Élément | Règles |
|---|---|
| Notion | `source_excerpt` retrouvé dans le texte OCR (comparaison normalisée, tolérance de 10 %) ; `importance` entre 1 et 5 ; `id` unique |
| `questions[]` | 3 distracteurs distincts, différents de la réponse et de même nature (année ↔ année, nombre ↔ nombre) ; `stem` ne contient pas la réponse |
| `false_statements[]` | différente de toutes les `true_statements` ; aucune négation triviale (« ne… pas » ajouté seul) |
| `cloze` | exactement un `___` ; la réponse n'apparaît pas ailleurs dans la phrase |
| `pair` | `left` ≤ 40 caractères, `right` ≤ 60 caractères |
| `tip` | ≤ 120 caractères ; aucun chiffre ni nom propre absent de la notion |

Si le taux d'éléments rejetés d'une leçon dépasse 30 %, un avertissement est enregistré dans `ai_runs` : c'est un signal de qualité à suivre pendant les tests.

---

## 7. Moteur d'activités

### 7.1 Registre

```
Activity
├── MCQ              ✅ V1
├── TRUE_FALSE       ✅ V1
├── FILL_BLANK       ✅ V1
├── MATCH            ✅ V1
├── SPEED_CHALLENGE  ✅ V1
├── FLASHCARD        ✅ V1
├── ORDER            🔜 V1.1 (chronologie, étapes d'un processus)
├── MEMORY           🔜 V2
└── OPEN_QUESTION    🔜 V2 (correction par l'IA)
```

Chaque type est une classe autonome côté serveur :

```python
class ActivityType(ABC):
    code: ClassVar[str]                      # "MCQ"
    knowledge_types: ClassVar[set[str]]      # types de notion compatibles
    difficulties: ClassVar[set[int]]         # {1, 2}
    base_duration_s: ClassVar[int]           # pour l'estimation de durée
    multi_knowledge: ClassVar[bool] = False  # MATCH, SPEED_CHALLENGE couvrent plusieurs notions

    def can_build(self, items: list[KnowledgeWithMaterial], difficulty: int) -> bool: ...
    def build(self, items, difficulty, rng) -> BuiltActivity: ...   # payload public + solution privée
    def grade(self, activity: BuiltActivity, response: dict) -> Grade: ...
```

Ajouter un jeu revient à écrire une classe côté serveur, l'enregistrer, écrire un widget Flutter et l'enregistrer. Le composeur, la notation et la mémorisation ne changent pas.

### 7.2 Compatibilité notion → activité

| Type de notion | MCQ | TRUE_FALSE | FILL_BLANK | MATCH | SPEED | FLASHCARD | ORDER* |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| date | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| person | ✓ « Qui suis-je ? » | ✓ | | ✓ | ✓ | ✓ | |
| place | ✓ | ✓ | | ✓ | ✓ | ✓ | |
| event | ✓ | ✓ | ✓ | ✓ | ✓ | | ✓ |
| term | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | |
| rule | ✓ | ✓ | ✓ | | ✓ | ✓ | |
| formula | ✓ | ✓ | ✓ | ✓ | | ✓ | |
| fact | ✓ | ✓ | ✓ | | ✓ | | |
| process | ✓ | ✓ | | | | | ✓ |
| classification | ✓ | ✓ | | ✓ | ✓ | | |

\* ORDER en V1.1.

### 7.3 Contrats JSON des activités

`payload` est envoyé au téléphone. `solution` reste sur le serveur. La réponse de l'enfant est notée `response`.

| Type | `payload` | `response` |
|---|---|---|
| MCQ | `{prompt, choices:[{id,text}]}` | `{choice_id}` |
| TRUE_FALSE | `{statement}` | `{value: true\|false}` |
| FILL_BLANK | `{text: "… ___ …", hint?}` | `{text}` |
| MATCH | `{left:[{id,text}], right:[{id,text}]}` (colonne de droite mélangée) | `{pairs:[[left_id,right_id]…]}` |
| SPEED_CHALLENGE | `{time_limit_s: 30, statements:[{id,text}]}` (5 affirmations vrai/faux) | `{answers:[{id,value}], elapsed_ms}` |
| FLASHCARD | `{front, back}` | `{self_assessment: "knew"\|"didnt_know"}` |

Réponse de correction, commune à tous les types :

```json
{
  "result": "incorrect",
  "score": 0.0,
  "correct_answer": "1789",
  "tip": "1789 = Révolution française.",
  "explanation": "La Révolution française commence en 1789…",
  "details": []
}
```

`details` décrit, pour MATCH et SPEED_CHALLENGE, le résultat élément par élément : `[{id, correct, expected}]`.

---

## 8. Composition d'une séance

### 8.1 Première révision d'une leçon

| Bloc | Contenu | Règle de sélection |
|---|---|---|
| 🧠 Échauffement | 3 activités faciles (difficulté 1 : MCQ, TRUE_FALSE) | les 3 notions les plus importantes |
| 🎯 Approfondissement | 3 activités intermédiaires (difficulté 2 : FILL_BLANK, MCQ inversé, FLASHCARD) | les 3 notions suivantes ; si la leçon en a moins de 6, on reprend les plus importantes avec un autre format |
| 🧩 Association | 1 MATCH de 4 à 5 paires (3 accepté pour les petites leçons) | notions ayant une `pair`, en priorité celles non vues dans les blocs précédents |
| ⚡ Défi rapide | 1 SPEED_CHALLENGE : 5 vrai/faux en 30 s | mélange de `true_statements` et de `false_statements` |
| 🔄 Reprise des erreurs | 1 activité par notion ratée (3 au maximum) | **format différent** de celui qui a été raté ; ajoutée à la fin par `POST /sessions/{id}/replay` |

Règles communes :

- une même notion n'apparaît pas deux fois dans les blocs 1 et 2 ;
- deux activités consécutives ne sont pas du même type : le composeur essaie les ordres possibles des notions d'un bloc et leurs formats avant, en dernier recours, d'assouplir la difficulté ;
- les notions d'importance ≤ 2 ne sont utilisées que si la leçon a moins de 6 notions d'importance ≥ 3 ;
- tirage aléatoire reproductible : la graine est enregistrée avec la séance, pour pouvoir rejouer un bug.

### 8.2 Durée estimée

`durée = Σ base_duration_s + 5 s de transition par activité + provision pour la reprise`

| Type | Durée de base |
|---|---|
| MCQ | 20 s |
| TRUE_FALSE | 12 s |
| FILL_BLANK | 30 s |
| FLASHCARD | 15 s |
| MATCH | 60 s |
| SPEED_CHALLENGE | 40 s |

- Provision pour la reprise : 30 % × 3 × 20 s.
- Correction : 8 s par activité.
- L'estimation est arrondie à la minute supérieure.
- Elle sera recalibrée avec les durées réelles mesurées (`attempts.duration_ms`).

### 8.3 Révisions suivantes (leçon déjà travaillée)

1. Priorité de chaque notion = `importance × (100 − score_maîtrise) / 100`, majorée ×1,5 si sa révision est due.
2. Les notions avec un score ≥ 90 et une révision non due sont exclues : *on ne refait pas 10 questions sur ce qu'Emma connaît déjà*.
3. Même structure de blocs, avec des difficultés adaptées au score :
   - score < 50 : difficulté 1 ;
   - 50 à 79 : difficulté 2 ;
   - ≥ 80 : difficulté 2 ou 3.
4. Si moins de 3 notions restent à travailler, la séance est courte (blocs 1 et 4 seulement) et l'écran 4 l'annonce : « Révision express : 2 min ». Le défi rapide est alors complété par d'autres notions de la leçon si besoin. S'il ne reste rien à travailler, l'API répond « rien à réviser » (prochaine révision affichée).

### 8.4 Séance « Revoir mes erreurs »

Elle ne porte que sur les notions `to_review` et `not_mastered` de la séance d'origine. Elle contient 2 activités par notion, dans des formats différents, sans association ni défi.

---

## 9. Notation

### 9.1 Score d'une activité (0 à 1)

| Type | Calcul |
|---|---|
| MCQ, TRUE_FALSE | 1 ou 0 |
| FILL_BLANK | 1 si la réponse normalisée (minuscules, sans accents ni ponctuation) est dans `answers`. Fautes tolérées : aucune jusqu'à 4 caractères, 1 de 5 à 8 caractères, 2 au-delà (distance de Damerau-Levenshtein). Nombres et années : correspondance exacte |
| MATCH | paires justes / paires totales |
| SPEED_CHALLENGE | réponses justes / 5 ; une affirmation sans réponse compte faux |
| FLASHCARD | `knew` = 1, `didnt_know` = 0 (auto-évaluation) |

Résultat affiché : `correct` si le score vaut 1, `partial` s'il est ≥ 0,5, `incorrect` sinon.

### 9.2 Note de la séance

`note /10 = 10 × moyenne des scores des activités principales`, arrondie à 0,5. La reprise des erreurs n'entre pas dans la note, mais elle compte pour la maîtrise.

### 9.3 Résultat par notion dans la séance

Chaque tentative produit une preuve par notion couverte, pondérée ainsi :

| Source | Poids |
|---|---|
| difficulté 1 | 0,6 |
| difficulté 2 | 0,8 |
| difficulté 3 | 1,0 |
| vrai/faux, défi rapide, flashcard | × 0,5 (une réponse au hasard est possible, ou c'est une auto-évaluation) |

`taux_séance(notion) = Σ(poids × résultat) / Σ(poids)`

| Statut dans le bilan | Condition |
|---|---|
| ✅ Maîtrisée | taux ≥ 0,8 |
| 🟠 À revoir | 0,5 ≤ taux < 0,8 |
| 🔴 Non maîtrisée | taux < 0,5 |

Une notion ratée puis réussie en reprise obtient un taux de 0,5 environ, donc 🟠 à revoir. C'est voulu : elle reviendra à la prochaine révision.

---

## 10. Mémorisation et prochaine révision

Chaque notion a, pour chaque apprenant, un **score de maîtrise** de 0 à 100 % (celui qui s'affiche) et une **boîte** de 1 à 5 (qui sert à planifier les rappels).

### 10.1 Mise à jour en fin de séance

- Première fois : `score = 100 × taux_séance`, et la boîte de départ est 1 (une notion réussie du premier coup passe donc en boîte 2, rappel à J+2).
- Ensuite : `score = 0,6 × (100 × taux_séance) + 0,4 × score_précédent`.

Boîte :

| Taux de la séance | Effet sur la boîte |
|---|---|
| ≥ 0,8 | boîte + 1 (5 au maximum) |
| entre 0,5 et 0,8 | inchangée (1 au minimum) |
| < 0,5 | retour en boîte 1 |

Intervalles avant la prochaine révision :

| Boîte | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| Prochaine révision | J+1 | J+2 | J+4 | J+7 | J+14 |

### 10.2 Prochaine révision d'une leçon

C'est la date la plus proche parmi les notions d'importance ≥ 3, affichée sur le bilan et l'accueil. Si toutes ces notions ont un score ≥ 90 et sont en boîte 5, la leçon est marquée « maîtrisée ✓ ».

Exemple de ce que le moteur connaît :

```
Apprenant
├── Révolution française
│   ├── 1789              92 %  boîte 4 → 30 sept.
│   ├── Louis XVI         84 %  boîte 3 → 27 sept.
│   ├── États généraux    42 %  boîte 1 → demain
│   └── Bastille          96 %  boîte 4 → 30 sept.
└── Fractions
    ├── numérateur        91 %
    ├── dénominateur      88 %
    └── comparaison       51 %
```

---

## 11. API

Base : `/v1`. Documentation OpenAPI générée : `/docs`.

Deux sortes de jetons, envoyés en `Authorization: Bearer …` :
- **parent** : jeton d'accès de 15 minutes et jeton de renouvellement de 30 jours ; donne accès aux enfants de sa famille ;
- **appareil enfant** : obtenu en échangeant un code de liaison ; ne donne accès qu'au profil de cet enfant.

Une ressource hors de son périmètre répond 404, comme si elle n'existait pas.

**Comptes et liaison (parent)**

| Méthode | Route | Rôle |
|---|---|---|
| POST | `/v1/auth/register` | `{email, password, accepted_privacy_policy}` → jetons parent |
| POST | `/v1/auth/login` · `/v1/auth/refresh` · `/v1/auth/logout` | connexion, renouvellement (avec rotation), déconnexion |
| POST | `/v1/auth/password-reset` | envoi d'un lien de réinitialisation (réponse identique que l'e-mail existe ou non) |
| POST | `/v1/auth/password-reset/confirm` | `{token, new_password}` : nouveau mot de passe, déconnexion des autres sessions |
| GET | `/v1/parent` | compte du parent connecté |
| DELETE | `/v1/parent` | supprime le compte, la famille et tous les enfants |
| GET · POST | `/v1/children` | liste · création `{display_name, grade, avatar, parental_consent: true}` |
| PATCH · DELETE | `/v1/children/{id}` | modification · suppression de l'enfant et de toutes ses données |
| POST | `/v1/children/{id}/link-codes` | → `{code: "482731", qr: "ludifun://link/<jeton>", expires_at}` |
| GET · DELETE | `/v1/children/{id}/devices[/{device_id}]` | appareils liés · délier |
| GET | `/v1/children/{id}/dashboard?weeks=4` | tableau de bord (écran P3) : `this_week`, `subjects`, `to_strengthen`, `reviews_due`, `weeks`, `trend`, `activities_this_week` |
| GET | `/v1/children/{id}/history?limit=20&before=` | séances (écran P4) : `{sessions, next_before}` |

**Espace enfant** (jeton d'appareil ; un parent peut aussi appeler ces routes avec `?child_id=`)

| Méthode | Route | Rôle |
|---|---|---|
| POST | `/v1/link` | `{code}` ou `{qr_token}` → `{child, token}` (écran 0, sans authentification) |
| GET | `/v1/me` | profil de l'enfant |
| DELETE | `/v1/me/device` | l'appareil se délie lui-même (« Ce n'est pas moi » à l'écran 0) |
| GET | `/v1/me/mission` | mission du jour (écran 1) : `{lesson, reason: due \| not_mastered \| latest, estimated_minutes}`, `lesson: null` si tout est à jour |
| GET | `/v1/lessons` | Dernières leçons (écran 1) |
| POST | `/v1/lessons` | *multipart* `pages[]` (1 à 6 images) → **202** `{id, status: "uploaded"}`, traitement en arrière-plan |
| GET | `/v1/lessons/{id}` | Statut et, si `ready`, leçon et notions (écrans 3 et 4) |
| PATCH | `/v1/lessons/{id}` | `{grade}` : correction du niveau par l'enfant |
| POST | `/v1/lessons/{id}/retry` | Relance une analyse échouée pour cause `ai_error` (le texte OCR est déjà stocké) |
| DELETE | `/v1/lessons/{id}` | Supprime la leçon et son historique |
| POST | `/v1/lessons/{id}/sessions` | `{kind: "auto"}` → séance (écran 4) ; reprend la séance en cours si elle a moins de 24 h ; 409 `nothing_to_review` s'il n'y a rien à réviser |
| GET | `/v1/sessions/{id}` | Reprise d'une séance interrompue |
| POST | `/v1/sessions/{id}/attempts` | `{item_id, response, duration_ms}` → correction (écran 6) ; `{"skipped": true}` pour une activité que l'application ne sait pas afficher (ni notée, ni comptée dans la maîtrise) |
| POST | `/v1/sessions/{id}/replay` | Génère le bloc de reprise des erreurs → `items[]` (éventuellement vide) ; une fois toutes les activités principales répondues ; idempotent |
| POST | `/v1/sessions/{id}/complete` | Clôture → bilan (écran 7) |
| POST | `/v1/sessions/{id}/errors-session` | Crée la séance « Revoir mes erreurs » |

### 11.1 Exemples

**`GET /v1/lessons/{id}`** pendant l'analyse, puis quand elle est prête :

```json
{ "id": "…", "status": "analyzing", "steps": { "reading": "done", "analyzing": "running", "generating": "pending" } }
```
```json
{
  "id": "…", "status": "ready",
  "subject": "history", "grade": "CM1", "title": "La Révolution française",
  "objective": "Connaître les principales notions de la Révolution française",
  "knowledge": [ { "id": "…", "label": "1789", "statement": "…", "importance": 5, "type": "date" } ],
  "next_review_at": null
}
```

**`POST /v1/lessons/{id}/sessions`** :

```json
{
  "id": "…", "kind": "first",
  "objective": "Connaître les principales notions de la Révolution française",
  "estimated_duration_min": 8,
  "items": [
    { "id": "…", "position": 1, "block": "warmup", "type": "MCQ", "difficulty": 1,
      "payload": { "prompt": "Quelle année marque le début de la Révolution française ?",
                   "choices": [ {"id":"a","text":"1492"}, {"id":"b","text":"1789"},
                                {"id":"c","text":"1914"}, {"id":"d","text":"1945"} ] } }
  ]
}
```

**`POST /v1/sessions/{id}/complete`** :

```json
{
  "score_on_10": 8.0,
  "counts": { "mastered": 7, "to_review": 2, "not_mastered": 1 },
  "knowledge": [
    { "id": "…", "label": "États généraux", "status": "to_review", "session_rate": 0.55, "mastery": 42 }
  ],
  "next_review_at": "2026-09-25",
  "can_review_errors": true
}
```

### 11.2 Robustesse du traitement des leçons

- L'analyse tourne en tâche de fond dans le processus de l'API (V1). Au démarrage, une analyse interrompue depuis plus de 10 minutes (redémarrage du serveur) passe en échec `ai_error` : elle se relance sans nouvelle photo si le texte avait déjà été lu (`can_retry`).
- Une file de tâches (Arq ou Celery avec Redis) remplacera la tâche de fond quand l'API tournera sur plusieurs instances ; seul `lesson_processing.py` changera.
- Une réponse envoyée deux fois en même temps (double appui) reçoit `409 already_answered`.

### 11.3 Erreurs

Format unique : `{"error": {"code": "lesson_unreadable", "message": "…"}}`.

| Code HTTP | Cas |
|---|---|
| 401 | jeton absent ou invalide |
| 404 | ressource absente ou appartenant à un autre appareil |
| 409 | séance déjà terminée, ou activité déjà répondue |
| 413 | image trop lourde |
| 415 | format non supporté |
| 422 | entrée invalide |
| 429 | limite de débit atteinte |
| 503 | IA indisponible |

---

## 12. Base de données PostgreSQL

Migrations avec **Alembic**. Identifiants en UUID, dates en `timestamptz`.

> **Évolution V1 élargie (migration `0002`, étape 6)** : les tables `devices` et `learners` de la migration `0001` sont remplacées par le modèle famille ci-dessous. `learner_id` devient `child_id` dans `lessons`, `sessions` et `knowledge_mastery` ; le reste du schéma ne change pas.
>
> Référence exécutable : `backend/app/db/models.py` et les migrations. Par rapport au SQL ci-dessous, elles ajoutent des index sur les clés étrangères utilisées par les suppressions en cascade (`sessions.lesson_id`, `ai_runs.lesson_id`, et en `0002` les clés vers `children` et `families`) et des contrôles supplémentaires (`page_count` 1-6, `difficulty` 1-3, `score` et `result` 0-1, `weight` ]0-1]).

```sql
CREATE TABLE parents (
  id               uuid PRIMARY KEY,
  email            text NOT NULL UNIQUE,         -- stocké en minuscules
  password_hash    text NOT NULL,                -- argon2id
  privacy_accepted_at timestamptz NOT NULL,
  email_verified_at   timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  last_login_at    timestamptz
);

-- Famille : un parent en V1, un second parent en V5, sans migration des enfants.
CREATE TABLE families (
  id          uuid PRIMARY KEY,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE family_members (
  family_id   uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  parent_id   uuid NOT NULL REFERENCES parents(id) ON DELETE CASCADE,
  role        text NOT NULL CHECK (role IN ('owner','member')),
  PRIMARY KEY (family_id, parent_id)
);

CREATE TABLE children (
  id               uuid PRIMARY KEY,
  family_id        uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  display_name     text NOT NULL,                -- prénom ou pseudo
  grade            text NOT NULL,                -- CP … 3e
  avatar           text,
  parental_consent_at timestamptz NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now()
);

-- Appareils de l'enfant, liés par code ou QR code.
CREATE TABLE devices (
  id            uuid PRIMARY KEY,
  child_id      uuid NOT NULL REFERENCES children(id) ON DELETE CASCADE,
  token_hash    bytea NOT NULL UNIQUE,          -- SHA-256 du jeton, jamais le jeton en clair
  name          text,                            -- « Tablette de la cuisine »
  created_at    timestamptz NOT NULL DEFAULT now(),
  last_seen_at  timestamptz,
  revoked_at    timestamptz
);

CREATE TABLE link_codes (
  id            uuid PRIMARY KEY,
  child_id      uuid NOT NULL REFERENCES children(id) ON DELETE CASCADE,
  code_hash     bytea NOT NULL,                  -- code à 6 chiffres, haché
  qr_token_hash bytea NOT NULL UNIQUE,           -- jeton long contenu dans le QR code
  created_at    timestamptz NOT NULL DEFAULT now(),
  expires_at    timestamptz NOT NULL,            -- 10 minutes ; un nouveau code annule le précédent
  used_at       timestamptz
);

CREATE TABLE password_reset_tokens (
  id            uuid PRIMARY KEY,
  parent_id     uuid NOT NULL REFERENCES parents(id) ON DELETE CASCADE,
  token_hash    bytea NOT NULL UNIQUE,
  created_at    timestamptz NOT NULL DEFAULT now(),
  expires_at    timestamptz NOT NULL,            -- 1 heure
  used_at       timestamptz
);

CREATE TABLE refresh_tokens (
  id            uuid PRIMARY KEY,
  parent_id     uuid NOT NULL REFERENCES parents(id) ON DELETE CASCADE,
  token_hash    bytea NOT NULL UNIQUE,
  expires_at    timestamptz NOT NULL,
  revoked_at    timestamptz,
  replaced_by   uuid REFERENCES refresh_tokens(id) ON DELETE SET NULL
);

CREATE TABLE lessons (
  id               uuid PRIMARY KEY,
  child_id         uuid NOT NULL REFERENCES children(id) ON DELETE CASCADE,
  status           text NOT NULL CHECK (status IN ('uploaded','reading','analyzing','generating','ready','failed')),
  failure_reason   text CHECK (failure_reason IN ('unreadable','not_a_lesson','too_long','ai_error')),
  subject          text,
  grade            text,
  grade_confidence real,
  title            text,
  objective        text,
  summary          text,
  page_count       smallint NOT NULL,
  analysis         jsonb,                        -- sortie normalisée complète (§6.2)
  prompt_versions  jsonb,                        -- {"ocr":"v1","analysis":"v1","material":"v1"}
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX lessons_child_recent ON lessons (child_id, created_at DESC);

CREATE TABLE lesson_pages (
  lesson_id   uuid NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
  page_index  smallint NOT NULL,
  ocr_text    text NOT NULL,                     -- le texte seulement : l'image n'est jamais stockée
  quality     text NOT NULL CHECK (quality IN ('good','partial','unreadable')),
  PRIMARY KEY (lesson_id, page_index)
);

CREATE TABLE knowledge_items (
  id              uuid PRIMARY KEY,
  lesson_id       uuid NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
  key             text NOT NULL,                 -- "k1"
  type            text NOT NULL,
  label           text NOT NULL,
  statement       text NOT NULL,
  importance      smallint NOT NULL CHECK (importance BETWEEN 1 AND 5),
  attributes      jsonb NOT NULL DEFAULT '{}',
  relations       jsonb NOT NULL DEFAULT '[]',
  source_excerpt  text NOT NULL,
  position        smallint NOT NULL,
  UNIQUE (lesson_id, key)
);

CREATE TABLE knowledge_material (
  knowledge_id    uuid PRIMARY KEY REFERENCES knowledge_items(id) ON DELETE CASCADE,
  material        jsonb NOT NULL,                -- §6.3, après validation
  rejected        jsonb NOT NULL DEFAULT '[]',   -- éléments écartés (analyse qualité)
  prompt_version  text NOT NULL
);

CREATE TABLE sessions (
  id                     uuid PRIMARY KEY,
  child_id               uuid NOT NULL REFERENCES children(id) ON DELETE CASCADE,
  lesson_id              uuid NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
  kind                   text NOT NULL CHECK (kind IN ('first','review','errors')),
  parent_session_id      uuid REFERENCES sessions(id) ON DELETE SET NULL,
  status                 text NOT NULL CHECK (status IN ('active','completed','abandoned')),
  objective              text NOT NULL,
  estimated_duration_s   integer NOT NULL,
  seed                   bigint NOT NULL,
  score_on_10            numeric(3,1),
  started_at             timestamptz NOT NULL DEFAULT now(),
  completed_at           timestamptz
);
CREATE INDEX sessions_child ON sessions (child_id, started_at DESC);

CREATE TABLE session_items (
  id              uuid PRIMARY KEY,
  session_id      uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  position        smallint NOT NULL,
  block           text NOT NULL CHECK (block IN ('warmup','core','match','speed','replay')),
  activity_type   text NOT NULL,
  difficulty      smallint NOT NULL,
  knowledge_ids   uuid[] NOT NULL,
  payload         jsonb NOT NULL,                -- envoyé au téléphone
  solution        jsonb NOT NULL,                -- jamais envoyé avant la réponse
  UNIQUE (session_id, position)
);

CREATE TABLE attempts (
  id               uuid PRIMARY KEY,
  session_item_id  uuid NOT NULL UNIQUE REFERENCES session_items(id) ON DELETE CASCADE,
  response         jsonb NOT NULL,
  score            numeric(3,2) NOT NULL,
  duration_ms      integer,
  created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE attempt_evidence (                  -- une ligne par notion couverte par la tentative
  attempt_id    uuid NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
  knowledge_id  uuid NOT NULL REFERENCES knowledge_items(id) ON DELETE CASCADE,
  result        numeric(3,2) NOT NULL,
  weight        numeric(3,2) NOT NULL,
  PRIMARY KEY (attempt_id, knowledge_id)
);

CREATE TABLE knowledge_mastery (
  child_id           uuid NOT NULL REFERENCES children(id) ON DELETE CASCADE,
  knowledge_id       uuid NOT NULL REFERENCES knowledge_items(id) ON DELETE CASCADE,
  score              smallint NOT NULL CHECK (score BETWEEN 0 AND 100),
  box                smallint NOT NULL CHECK (box BETWEEN 1 AND 5),
  next_review_at     timestamptz NOT NULL,
  last_practiced_at  timestamptz NOT NULL,
  sessions_count     integer NOT NULL DEFAULT 1,
  PRIMARY KEY (child_id, knowledge_id)
);
CREATE INDEX mastery_due ON knowledge_mastery (child_id, next_review_at);

CREATE TABLE ai_runs (                           -- coût, latence et qualité de chaque appel IA
  id             uuid PRIMARY KEY,
  lesson_id      uuid REFERENCES lessons(id) ON DELETE SET NULL,
  stage          text NOT NULL CHECK (stage IN ('ocr','analysis','material')),
  provider       text NOT NULL,
  model          text NOT NULL,
  prompt_version text NOT NULL,
  input_tokens   integer,
  output_tokens  integer,
  latency_ms     integer NOT NULL,
  status         text NOT NULL CHECK (status IN ('ok','invalid_output','refused','error')),
  warnings       jsonb NOT NULL DEFAULT '[]',
  created_at     timestamptz NOT NULL DEFAULT now()
);
```

Le contenu des leçons n'est jamais copié dans `ai_runs`, qui ne contient que des métadonnées. `ON DELETE SET NULL` conserve les statistiques de coût après la suppression d'une leçon.

---

## 13. Architecture FastAPI

```
backend/
├── pyproject.toml                  # dépendances, ruff, mypy, pytest
├── alembic.ini
├── migrations/versions/
├── app/
│   ├── main.py                     # création de l'app, montage /v1, gestion des erreurs
│   ├── config.py                   # Settings (pydantic-settings)
│   ├── api/
│   │   ├── deps.py                 # session DB, appareil courant, fournisseurs
│   │   ├── errors.py               # format d'erreur unique
│   │   └── v1/
│   │       ├── devices.py
│   │       ├── lessons.py
│   │       ├── sessions.py
│   │       ├── me.py
│   │       └── schemas.py          # modèles Pydantic d'entrée et de sortie
│   ├── domain/                     # Python pur : aucun import de FastAPI, SQLAlchemy ni SDK IA
│   │   ├── knowledge.py            # KnowledgeItem, KnowledgeMaterial, types
│   │   ├── validation.py           # validateurs §6.4
│   │   ├── text.py                 # normalisation, fautes tolérées, recherche approximative
│   │   ├── activities/
│   │   │   ├── base.py             # ActivityType, BuiltActivity, Grade
│   │   │   ├── registry.py
│   │   │   ├── mcq.py
│   │   │   ├── true_false.py
│   │   │   ├── fill_blank.py
│   │   │   ├── match.py
│   │   │   ├── speed_challenge.py
│   │   │   └── flashcard.py
│   │   ├── composer.py             # §8 : blocs, sélection, reprise, durée
│   │   ├── scoring.py              # §9 : note de séance, taux par notion
│   │   └── mastery.py              # §10 : score, boîtes, prochaine révision
│   ├── services/
│   │   ├── lesson_pipeline.py      # OCR → analyse → enrichissement, statuts, journal ai_runs (sans base)
│   │   ├── session_service.py      # créer, répondre, reprise, clôturer
│   │   └── report_service.py
│   ├── ai/
│   │   ├── ports.py                # OcrProvider, LLMProvider, PageImage, LLMResult
│   │   ├── factory.py              # fournisseurs selon la configuration
│   │   ├── schemas.py              # OcrResult, LessonAnalysis, KnowledgeMaterial (Pydantic)
│   │   ├── prompts/                # ocr.v1.md, analysis.v1.md, material.v1.md
│   │   ├── providers/
│   │   │   ├── claude.py
│   │   │   └── fake.py
│   │   └── ocr/
│   │       └── vision_llm.py
│   ├── db/
│   │   ├── base.py                 # moteur, session
│   │   ├── models.py               # tables SQLAlchemy (§12)
│   │   └── repositories.py
│   ├── security/
│   │   ├── tokens.py               # génération et vérification des jetons d'appareil
│   │   └── rate_limit.py
│   └── tools/
│       └── analyze.py              # CLI : python -m app.tools.analyze photo1.jpg photo2.jpg
└── tests/
    ├── fixtures/lessons/*.json     # leçons normalisées de référence (sans IA)
    ├── domain/                     # composeur, notation, mémorisation, chaque activité
    └── api/                        # parcours complets avec FakeProvider
```

Règles d'architecture :

- `domain/` ne dépend de rien. Il est testé à 100 % avec des leçons de référence en JSON, sans IA ni base.
- Le traitement d'une leçon s'exécute en V1 dans une tâche de fond (`BackgroundTasks`). Le passage à une vraie file (Arq ou Celery, avec Redis) ne concerne que `lesson_pipeline.py`.
- L'API est asynchrone (SQLAlchemy async + asyncpg).
- Infrastructure locale : `docker-compose.yml` lance PostgreSQL 16 et l'API.

---

## 14. Architecture Flutter

### 14.1 Choix techniques

| Besoin | Choix | Raison |
|---|---|---|
| État | **Riverpod** | testable, sans `BuildContext`, adapté au polling et aux séances |
| Navigation | **go_router** | routes déclaratives, liens profonds plus tard |
| HTTP | **dio** | intercepteur pour le jeton, délais, envoi multipart avec progression |
| Modèles | classes immuables écrites à la main (`fromJson`) ; **freezed + json_serializable** si leur nombre le justifie | pas d'étape de génération de code tant que les modèles restent peu nombreux |
| Photos | **image_picker** (V1), **cunning_document_scanner** (V1.1) | photo simple d'abord ; le recadrage automatique ensuite |
| Compression | **flutter_image_compress** | redimensionnement, JPEG, suppression des métadonnées EXIF |
| Jeton | **flutter_secure_storage** | stockage chiffré |

### 14.2 Arborescence

```
mobile/
├── pubspec.yaml
├── lib/
│   ├── main.dart
│   ├── app/
│   │   ├── app.dart                 # MaterialApp.router, thème, français
│   │   ├── router.dart              # routes ; redirection selon l'espace (aucun, parent, enfant)
│   │   ├── theme.dart               # couleurs, typographie adaptée aux enfants
│   │   └── widgets.dart             # éléments communs
│   ├── core/
│   │   ├── config.dart              # API_URL (--dart-define)
│   │   ├── session.dart             # identifiants de l'appareil (Riverpod), client API
│   │   ├── storage/credentials.dart # parent ou enfant, dans flutter_secure_storage
│   │   └── api/
│   │       ├── ludifun_api.dart     # routes /v1
│   │       ├── auth_interceptor.dart # jeton, renouvellement unique sur 401, appareil délié
│   │       └── api_exception.dart   # erreur API ou réseau → message affichable
│   ├── models/                      # lesson, knowledge, session, activity, feedback, report
│   └── features/
│       ├── start/                   # premier lancement : parent ou enfant
│       ├── parent/                  # Écrans P1 à P4 : compte, enfants, codes, tableau de bord
│       ├── link/                    # Écran 0 : code ou QR code (mobile_scanner)
│       ├── home/                    # Écran 1
│       │   ├── child_home_screen.dart
│       │   └── home_providers.dart  # mission, leçons (rafraîchies pendant une analyse)
│       ├── capture/                 # Écran 2
│       │   ├── capture_screen.dart
│       │   ├── capture_controller.dart   # pages gardées jusqu'à `ready`, puis effacées
│       │   └── image_compressor.dart
│       ├── analysis/                # Écran 3
│       │   ├── analysis_screen.dart      # interrogation toutes les 1,5 s
│       │   └── step_pacer.dart           # 800 ms minimum par étape
│       ├── lesson/                  # Écran 4
│       │   └── lesson_screen.dart
│       ├── session/                 # Écrans 5 et 6
│       │   ├── session_screen.dart
│       │   ├── session_controller.dart   # machine à états : question → correction → suivante → reprise → bilan
│       │   ├── feedback_view.dart
│       │   └── activities/
│       │       ├── activity_registry.dart
│       │       ├── mcq_view.dart
│       │       ├── true_false_view.dart
│       │       ├── fill_blank_view.dart
│       │       ├── match_view.dart
│       │       ├── speed_challenge_view.dart
│       │       └── flashcard_view.dart
│       └── report/                  # Écran 7
│           └── report_screen.dart
└── test/
    ├── activities/                  # tests de widgets par type d'activité
    └── session_controller_test.dart
```

### 14.3 Registre de widgets

```dart
typedef ActivityBuilder = Widget Function(
  SessionItem item,
  void Function(Map<String, dynamic> response) onSubmit,
);

const activityRegistry = <String, ActivityBuilder>{
  'MCQ': McqView.new,
  'TRUE_FALSE': TrueFalseView.new,
  'FILL_BLANK': FillBlankView.new,
  'MATCH': MatchView.new,
  'SPEED_CHALLENGE': SpeedChallengeView.new,
  'FLASHCARD': FlashcardView.new,
};
```

Un type inconnu (serveur plus récent que l'application) est sauté proprement : le client appelle `attempts` avec `{"skipped": true}`, et cette tentative n'est pas comptée dans la note.

### 14.4 Machine à états de la séance

```
loading → question ⇄ submitting → feedback → question (suivante)
                                          └→ (fin des items principaux) replay_loading → question (reprise) …
                                          └→ (fin) completing → report
```

---

## 15. Gestion des photos

| Étape | Où | Règle |
|---|---|---|
| Capture | téléphone | 1 à 6 pages, ordre modifiable |
| Compression | téléphone | côté long ≤ 2000 px, JPEG qualité 80, **métadonnées EXIF supprimées** (dont la position GPS) |
| Envoi | réseau | HTTPS, multipart, ≤ 8 Mo par page |
| Contrôle | serveur | type vérifié sur les octets du fichier (JPEG, PNG, WebP, HEIC converti), dimensions ≥ 600 px, 6 pages au maximum |
| Traitement | serveur | image gardée en mémoire le temps de l'OCR uniquement |
| Stockage | — | **aucun** : seul le texte OCR est conservé ; l'image n'est ni écrite sur disque, ni journalisée |
| Téléphone | téléphone | les photos restent dans un dossier temporaire de l'application jusqu'à `ready`, puis sont supprimées |

Exception encadrée : pour constituer le corpus de test (§17), les photos sont collectées **hors application**, avec l'accord explicite des familles testeuses, et stockées dans un espace privé de l'équipe.

---

## 16. Sécurité et données personnelles

### 16.1 Sécurité technique (V1)

- **Parent** : mot de passe haché avec argon2id (12 caractères minimum), jeton d'accès signé de 15 minutes, jeton de renouvellement de 30 jours avec rotation : réutiliser un ancien jeton révoque toute la chaîne. Connexion limitée à 5 essais par minute.
- **Liaison enfant** : code à 6 chiffres valable 10 minutes, à usage unique, annulé par tout nouveau code ; 10 essais par adresse IP toutes les 10 minutes et un **plafond global** d'échecs (300 par minute) contre une attaque répartie sur de nombreuses adresses. Le QR code contient un jeton aléatoire de 128 bits, pas le code. Le parent peut délier un appareil à tout moment.
- **E-mails** : tant qu'aucun fournisseur n'est branché, les messages sont journalisés en développement seulement ; en production, aucun lien n'est jamais écrit dans les journaux.
- Les limites de débit sont gardées en mémoire (une instance d'API) ; elles passeront dans un stockage partagé quand l'API tournera sur plusieurs instances.
- **Appareil enfant** : jeton aléatoire de 256 bits, stocké haché (SHA-256) côté serveur et dans `flutter_secure_storage` côté téléphone.
- **Séparation stricte** : un appareil enfant n'accède qu'aux données de son enfant, jamais au tableau de bord ni aux autres profils ; un parent n'accède qu'aux enfants de sa famille. Toute autre ressource renvoie 404. Des tests couvrent chaque route pour les deux rôles.
- HTTPS obligatoire (reverse proxy), HSTS, pas de CORS (application mobile uniquement).
- Limites de débit :
  - 20 leçons par jour et par appareil ;
  - 300 requêtes par minute et par appareil ;
  - plafond de coût IA journalier global, avec alerte.
- Toutes les entrées sont validées par Pydantic, avec des tailles maximales partout.
- Injection de prompt : le texte de la leçon est une donnée entre balises. Les sorties sont validées par schéma, les modèles n'ont accès à aucun outil, et un texte étrange donne au pire une leçon ratée.
- Secrets dans des variables d'environnement, jamais dans le code. Dépendances figées et analysées en intégration continue.
- Journaux sans contenu de leçon ni jeton.

### 16.2 Données personnelles (enfants)

- **Minimisation** : pour le parent, un e-mail ; pour l'enfant, un prénom ou pseudo, une classe et un avatar. Ni nom de famille, ni date de naissance, ni e-mail de l'enfant.
- **Consentement parental** recueilli à la création de chaque profil enfant (horodaté).
- Pas de photo conservée. La transcription exclut les en-têtes personnels.
- Effacement : `DELETE /v1/lessons/{id}`, `DELETE /v1/children/{id}` et `DELETE /v1/parent` suppriment tout, en cascade ; export des données d'un enfant sur demande.
- Conservation : suppression automatique d'un compte inactif depuis 12 mois, après un e-mail de prévenance.
- Fournisseurs d'IA : contrat de sous-traitance (DPA) et absence d'entraînement sur les données transmises. Hébergement de l'API et de la base dans l'UE.
- Pas de publicité, pas de traceur tiers, pas de classement.
- **Avant la bêta publique** : politique de confidentialité, registre des traitements, analyse d'impact (AIPD), vérification de l'e-mail du parent.

---

## 17. Tests avec de vraies leçons

C'est la mesure du succès de la V1.

### 17.1 Corpus

30 leçons photographiées, dont une majorité de photos de téléphone réalistes (angle, ombre, pliure), réparties ainsi :

| Critère | Répartition |
|---|---|
| Niveaux | 10 CP-CE2, 10 CM1-CM2, 10 collège |
| Matières | au moins 4 leçons par matière principale |
| Support | 10 manuscrites (cahier), 10 imprimées (manuel), 10 fiches ou photocopies |

Pour chaque leçon, un enseignant ou un parent annote `expected.json` : les notions indispensables, l'importance attendue et le niveau.

### 17.2 Mesures automatiques (`python -m app.tools.evaluate`, protocole dans `eval/README.md`)

| Mesure | Seuil V1 |
|---|---|
| Leçons analysées sans échec | ≥ 90 % |
| Matière correcte | ≥ 95 % |
| Niveau à ± 1 classe | ≥ 80 % |
| Rappel des notions indispensables | ≥ 85 % |
| Notions sans `source_excerpt` valide (inventions) | 0 |
| Éléments de matériel rejetés par les validateurs | ≤ 15 % |
| Durée photo → `ready` (2 pages, médiane) | ≤ 45 s |
| Coût IA par leçon | mesuré (`ai_runs`) — budget cible à fixer après la première mesure |

### 17.3 Évaluation humaine

Pour 10 leçons, un adulte joue la séance et note sur 5 :

- **pertinence** (on révise bien ce qui sera demandé) ;
- **justesse** (aucune erreur de contenu) ;
- **clarté** (vocabulaire adapté au niveau) ;
- **plaisir**.

Ensuite, 5 enfants testent en situation réelle, observés sans aide.

Critère de passage à la suite : **pertinence ≥ 4/5, justesse = 5/5 sur 90 % des séances, et 4 enfants sur 5 qui finissent la séance sans aide.**

---

## 18. Plan de développement

Ordre exact de réalisation. Chaque étape se termine par du code qui tourne, des tests verts et un commit.

**Recommandation :** remonter les tests sur de vraies leçons juste après le pipeline IA (étape 4), avant l'application. C'est la mission de la V1, et c'est là que se trouve le vrai risque. Si l'analyse n'est pas bonne, inutile de peaufiner les écrans.

| # | Étape | Contenu | Terminé quand… |
|---|---|---|---|
| 1 ✅ | **Socle** | réorganisation `backend/` selon §13, `pyproject`, ruff, mypy, pytest, docker-compose PostgreSQL, Alembic et première migration (§12), intégration continue GitHub Actions | `docker compose up` et `pytest` passent en intégration continue |
| 2 ✅ | **Domaine : connaissances et activités** | schémas `knowledge`, validateurs §6.4, registre et 6 types d'activités (`build` et `grade`), 3 leçons de référence en JSON | chaque activité est construite et corrigée par des tests unitaires |
| 3 ✅ | **Domaine : séance** | composeur §8, durée §8.2, notation §9, mémorisation §10 | une séance complète est simulée en test : réussites, erreurs, reprise, bilan, prochaine révision |
| 4 ✅ | **Pipeline IA** | ports, `VisionLLMOcr`, analyse, enrichissement, validation, relance ciblée, `ai_runs`, CLI `app.tools.analyze` | `python -m app.tools.analyze photo.jpg` affiche la leçon normalisée et une séance composée |
| 5 🟡 | **Premier test de qualité** | 10 premières leçons réelles, outil `app.tools.evaluate` (✅ prêt), ajustement des prompts (en attente des leçons) | les seuils §17.2 sont approchés ; rapport `eval/report.md` |
| 6 ✅ | **API : comptes et liaison** | migration `0002` (familles), inscription et connexion parent, profils enfants, codes et QR de liaison, appareils, jetons, séparation parent / enfant | un parent crée Emma, un appareil se lie par code ; tests de séparation sur chaque route |
| 7 ✅ | **API : leçons et séances** | leçons asynchrones avec statuts, séances, tentatives, reprise, bilan, « Revoir mes erreurs », mission du jour, journal `ai_runs`, limites de débit | parcours enfant complet testé en API avec `FakeProvider` |
| 8 ✅ | **API : tableau de bord parent** | séances et temps, réussite par matière, notions à renforcer, progression par semaine, historique | tableau de bord calculé sur un parcours simulé de plusieurs semaines |
| 9 ✅ | **Socle Flutter** | projet, go_router, Riverpod, dio, thème, premier lancement (parent ou enfant), stockage sécurisé des jetons | l'application démarre sur émulateur dans les deux espaces |
| 10 ✅ | **Espace enfant : écrans 0 à 4** | liaison par code / QR, accueil et mission du jour, photo et compression, analyse avec polling, résumé | code saisi → photo réelle → écran 4 sur un téléphone (validé en tests et dans un navigateur contre l'API ; essai sur un vrai téléphone à faire) |
| 11 | **Espace enfant : écrans 5 à 7** | contrôleur de séance, 6 widgets d'activités, correction, reprise, bilan | séance complète jouée de bout en bout sur un téléphone |
| 12 | **Espace parent : écrans P1 à P4** | compte, enfants, code et QR, tableau de bord, historique, suppression | un parent suit une semaine de révisions de son enfant |
| 13 | **Tests avec de vraies familles** | corpus complet de 30 leçons, évaluation humaine, 5 enfants et leurs parents ; comparaison des fournisseurs d'OCR | critères de passage §17.3 atteints |
| 14 | **Bêta Android** | Play Store en test fermé, confidentialité (§16.2), supervision | 20 familles testeuses |

Ensuite : V2 (jeux, missions, gamification), V3 (intelligence pédagogique), V4 (professeur IA), V5 (écosystème parent), V6 (iOS), selon [`vision.md`](vision.md) §5.

L'étape 5 (mesure sur de vraies leçons) se déroule **en parallèle** des étapes 6 à 8 : elle ne dépend que des leçons photographiées et d'une clé API. Ses résultats peuvent modifier les prompts, pas l'API.

---

## 19. Reprise du prototype existant

Le dépôt contient déjà un prototype exploratoire (commit initial). Il a validé la faisabilité : une photo passe par Claude vision, une banque de questions est produite, la correction et la maîtrise fonctionnent, 18 tests passent. La V1 le réorganise selon ce document.

| Élément du prototype | Décision |
|---|---|
| Profil enfant (prénom + classe) | **Rétabli** dans la V1 élargie, rattaché à une famille et à un compte parent (§12) |
| OCR et analyse en un seul appel | **Séparés** en étapes ① et ② derrière des interfaces |
| Notions (importance en 3 niveaux, types en français) | **Remplacées** par la structure normalisée §6.2 (importance 1 à 5, attributs typés, citation source) |
| Questions générées directement par l'IA | **Remplacées** par le matériel par notion (§6.3) et l'assemblage déterministe (§7) |
| Correction (normalisation, fautes tolérées, association) | **Reprise** dans `domain/scoring.py` et adaptée aux contrats §7.3 |
| Niveaux 0 à 5 et intervalles J+1…J+14 | **Repris** comme boîtes ; ajout du score en % (§10) |
| Sélection adaptative (priorité importance × faiblesse) | **Reprise** dans le composeur, structurée en blocs (§8) |
| `FakeLLM` | **Repris** comme `FakeProvider` |
| SQLite + SQLModel synchrone | **Remplacés** par PostgreSQL, SQLAlchemy async et Alembic |
| Écrans Flutter (`setState`) | **Réécrits** selon §14 (Riverpod, go_router, 7 écrans) ; les widgets d'activités servent de base |
