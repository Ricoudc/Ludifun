# Ludifun — Vision produit

> **Une plateforme de soutien scolaire personnalisée par IA.**
> L'enfant photographie sa leçon, l'IA comprend ce qu'il doit apprendre, choisit la
> meilleure façon de le lui faire apprendre, observe ses erreurs, change de méthode
> quand il bloque et programme les rappels. Le parent voit simplement où son enfant
> progresse et où il a besoin d'aide.

Ce document est le **fil directeur** du projet. Le cahier des charges
([`cahier-des-charges-v1.md`](cahier-des-charges-v1.md)) décrit précisément la version
en cours de construction ; ce document décrit où l'on va.

---

## 1. Principes

1. **Ce n'est pas à l'enfant de choisir comment apprendre** : c'est le moteur pédagogique qui choisit la méthode la plus adaptée à la leçon, à l'âge et à l'historique de l'enfant.
2. **Tout part des notions.** Une leçon est décomposée en notions (importance 1 à 5) ; chaque activité, chaque note et chaque rappel porte sur des notions.
3. **Une bibliothèque d'activités extensible.** Ajouter un jeu, une matière ou un type d'exercice ne doit pas obliger à modifier le moteur.
4. **Récompenser l'effort et la progression**, pas seulement les bonnes réponses : « Tu as réussi un exercice qui te posait problème hier ! » plutôt que « 10/10 ».
5. **Deux espaces séparés** : un espace enfant simple, coloré, sans statistiques ni pression ; un espace parent clair et factuel.
6. **Protection des enfants dès la conception** : données minimales, contrôle parental, aucune publicité, suppression facile, photos non conservées.
7. **Vérifier sur de vraies leçons avant d'élargir** : chaque version est mesurée (`eval/`) avant la suivante.

---

## 2. Les deux espaces

### 👨‍👩‍👧 Espace parent

- Compte parent ; création d'un ou plusieurs profils enfants (prénom, classe).
- Liaison d'un appareil enfant par **code à 6 chiffres ou QR code**.
- Tableau de bord par enfant : séances et temps de travail de la semaine, réussite par matière (🟢 🟠 🔴), notions à renforcer, progression semaine après semaine, types d'activités réalisées.
- Historique des leçons et des séances ; recommandations ; objectifs (plus tard).
- **Assistant parent** : « Que doit travailler Emma cette semaine ? », « Comment puis-je l'aider ? ». L'IA répond à partir des données réelles de l'enfant et propose une petite activité à faire ensemble.
- Paramètres, gestion des appareils liés, suppression des données.

### 👧 Espace enfant

- Accueil : « 👋 Bonjour Emma ! », **mission du jour** (leçon, durée), bouton COMMENCER.
- Ses leçons, missions, jeux, défis, récompenses, niveau et progrès personnels, sans statistiques complexes.
- Photographier une nouvelle leçon. Le parent peut aussi photographier la leçon pour son enfant.

Un parent peut suivre plusieurs enfants ; chaque enfant garde entièrement ses leçons, résultats, difficultés, historique, récompenses et profil d'apprentissage.

---

## 3. Le moteur pédagogique

```
📸 Photo(s) ─► améliorer ─► OCR / vision ─► analyse pédagogique ─► NOTIONS (importance 1-5)
                                                                      │
          historique de l'enfant, erreurs, âge, matière ──────────────┤
                                                                      ▼
                                             STRATÉGIE : quelles activités, dans quel ordre
                                                                      │
                                                                      ▼
                                     MISSION : suite d'activités tirées de la bibliothèque
                                                                      │
                                       réponses ─► évaluation ─► adaptation en temps réel
                                                                      │
                                                                      ▼
                                   maîtrise par notion (0-5, %) ─► répétition espacée
                                                                      │
                                                                      ▼
                                                      tableau de bord et assistant parent
```

### 3.1 L'IA choisit les activités

Entrées : leçon, niveau et âge, matière, notions, historique et erreurs de l'enfant.
Sortie : une **mission**, c'est-à-dire une suite d'activités avec un objectif.

| Matière | Exemple de stratégie |
|---|---|
| Histoire | frise chronologique → association dates / événements → quiz → question ouverte → défi |
| Géographie | carte → coloriage → localisation → quiz |
| Mathématiques | exemple visuel → exercice guidé → exercice autonome → problème → défi |
| Sciences | schéma à légender → classement → cartes mémoire → « explique-moi » |

**Choix d'architecture.** L'IA propose une **stratégie** parmi les activités réellement disponibles dans la bibliothèque. Des règles vérifient cette stratégie (durée, difficulté, variété, notions couvertes) et l'assemblent. En cas de doute ou de panne, le composeur à règles actuel prend le relais. On obtient ainsi l'intelligence de l'IA sans en dépendre pour que l'enfant puisse réviser.

### 3.2 Adaptation en temps réel

- Réussites répétées : la difficulté **augmente** (on passe de reconnaître à se rappeler, puis à appliquer).
- Échecs : la difficulté **diminue**. Après 3 échecs sur une même notion, l'application change de méthode : « 💡 On va essayer autrement ». Elle enchaîne alors une représentation visuelle, une association, un exercice simple, puis une question, avant de revenir au niveau initial.

### 3.3 Maîtrise et répétition espacée

- Chaque notion a un niveau de 0 à 5 (jamais étudiée → très bien maîtrisée) et un score en %.
- Les rappels sont programmés à J+1, J+2, J+4, J+7, J+14. Une notion ratée revient plus vite.

### 3.4 Missions et gamification

- Une mission a un thème et un objectif (« 🚀 Les planètes : connaître le système solaire ») et enchaîne 4 à 6 activités variées, jusqu'au défi final.
- L'enfant gagne de l'XP, des niveaux, des badges, des séries de jours et des défis. Ces récompenses sont liées à l'effort et à la progression.

### 3.5 Professeur IA

À terme, l'enfant dialogue avec l'IA (à l'écrit puis à l'oral) : « Explique-moi cette leçon ». L'IA pose des questions, reformule, donne des exemples, fait parler l'enfant et vérifie sa compréhension, avec un vocabulaire adapté à son âge.

---

## 4. La bibliothèque d'activités

Chaque activité est un module indépendant : une classe côté serveur (construction et correction) et un widget côté application. Chaque module déclare les types de notions, les matières et les niveaux qu'il sert, sa difficulté, sa durée, et s'il a besoin d'images, d'une carte ou de la voix.

| Famille | Activités | Version |
|---|---|---|
| 🧠 Mémorisation | QCM, vrai/faux, cartes mémoire, mots à compléter, association, défi rapide | **V1** ✅ |
| 🧠 Mémorisation | memory, questions ouvertes | V2 / V4 |
| ✍️ Exercices | calcul, problèmes, conjugaison, grammaire, orthographe, dictée, classement, transformations | V2-V3 |
| 🎨 Visuel | coloriage, schéma à compléter, image à annoter, frise chronologique | V2 |
| 🧩 Jeux | puzzle, memory, intrus, énigmes, parcours, défis | V2 |
| 🗺️ Géographie | carte interactive, localisation, coloriage de zones, capitales, reliefs | V2 |
| 🔬 Sciences | schémas, cycles, légendes, classement, expériences virtuelles | V2-V3 |
| 🔊 Oral | questions vocales, lecture, « explique-moi », conversation | V4 |

Matières de la V1 : français, mathématiques, histoire, géographie, sciences. Anglais, langues, EMC et technologie viendront ensuite ; chaque matière est une donnée, pas du code.

---

## 5. Versions

| Version | Objectif | Contenu | État |
|---|---|---|---|
| **V0 — Prototype** | vérifier le concept | photo → IA → leçon → activités → résultat | ✅ moteur côté serveur (étapes 1 à 4), 🟡 mesure sur de vraies leçons (étape 5) |
| **V1 — Première application Android** | un vrai usage en famille | **Parent** : compte, profils enfants, code / QR, tableau de bord, progression. **Enfant** : connexion par code, photo, analyse, QCM, cartes mémoire, vrai/faux, association, texte à trous, défi, bilan. **IA** : OCR, analyse, génération, correction, maîtrise, répétition espacée | 🔨 en cours |
| **V2 — Application ludique** | donner envie de revenir | coloriage, memory, puzzles, cartes, frises, missions, XP, badges, niveaux, défis quotidiens | |
| **V3 — Intelligence pédagogique** | l'IA choisit et s'adapte | stratégie choisie par l'IA, adaptation en temps réel, difficulté dynamique, plan de révision, recommandations, analyse des erreurs récurrentes | |
| **V4 — Professeur IA** | apprendre en parlant | voix, conversation, lecture, explication orale, questions ouvertes, évaluation orale | |
| **V5 — Écosystème parent** | accompagner | assistant parent, objectifs, rapports hebdomadaires, calendrier, notifications | |
| **V6 — iOS** | toutes les familles | iPhone, iPad, synchronisation, notifications, App Store | |

Déjà présent dans le moteur et remonté en V1 par rapport au découpage initial : répétition espacée, reprise des erreurs en fin de séance, choix des notions fragiles. L'application Flutter est unique pour Android et iOS : la V6 est un travail de publication et d'ajustements, pas une réécriture.

---

## 6. Architecture cible

```
Flutter (Android, iOS, tablette) ── espace parent │ espace enfant
        │
FastAPI /v1 ── comptes et liaison, leçons, missions, progression, assistant
        │
Orchestrateur pédagogique
  ├── OCR / vision              (fournisseur interchangeable)
  ├── analyse pédagogique       (notions)
  ├── génération du matériel    (par notion, validé)
  ├── stratégie de mission      (IA, bornée par la bibliothèque)      V3
  ├── évaluation                (règles ; IA pour les réponses libres)
  ├── adaptation                (en séance)                           V3
  └── planification             (maîtrise, répétition espacée)
        │
PostgreSQL ── parent → famille → enfant → leçon → notion → activité → réponse → progression
```

Chaque brique IA passe par une interface : on peut changer de modèle ou de fournisseur sans toucher au reste.

---

## 7. Sécurité, enfants et RGPD

- Séparation stricte parent / enfant : un appareil enfant n'accède qu'aux données de son profil ; seul le parent voit le tableau de bord et gère les profils.
- Données minimales : prénom ou pseudo et classe pour l'enfant ; e-mail pour le parent.
- Consentement parental recueilli à la création du profil enfant (enfant de moins de 15 ans en France).
- Photos non conservées après analyse ; données vocales (V4) traitées sans stockage par défaut.
- Conservation limitée, suppression d'un enfant ou du compte en un geste, export des données.
- Aucune publicité, aucun traceur tiers, aucun classement entre enfants.

---

## 8. Tests réels, avant toute commercialisation

Protocole et outils dans [`eval/`](../eval/README.md). Exemples de corpus : une dictée de CP, une leçon de maths de CE2, une leçon d'histoire de CM1, une carte de géographie, une leçon de sciences, une leçon de collège.

Questions auxquelles chaque version doit répondre :
- L'IA comprend-elle correctement la leçon ?
- Les exercices sont-ils pertinents et justes ?
- L'enfant comprend-il les consignes seul ?
- Les jeux font-ils réellement travailler la notion ?
- Le système détecte-t-il correctement les difficultés ?
