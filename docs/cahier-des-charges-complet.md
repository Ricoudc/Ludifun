# Cahier des charges complet — Application mobile IA d'accompagnement scolaire personnalisé

**Version 1.1 — Document de conception fonctionnelle et technique** (1.1 : directives pour l'IA de développement, §112-149)
Plateformes cibles : Android en priorité, puis iOS / iPadOS.
Technologies : Flutter + FastAPI + PostgreSQL + IA multimodale.

> Document de référence produit, rédigé par le porteur du projet. Il remplace
> [`vision.md`](vision.md) comme fil directeur. Sa traduction en travaux techniques, à partir
> de ce qui est déjà construit, est dans
> [`specification-technique.md`](specification-technique.md) ; les références « CDC §n »
> renvoient aux sections de ce document.

---

## 1. Vision du projet

### 1.1 Concept

L'application est un assistant scolaire intelligent, personnalisé et ludique, destiné aux enfants et à leurs parents.

Son objectif n'est pas simplement de scanner une leçon, produire un résumé, générer dix questions, donner une note. L'application doit se comporter comme un véritable tuteur pédagogique numérique.

Elle doit comprendre :

- ce que l'enfant doit apprendre ;
- son âge et son niveau scolaire ;
- les notions importantes de la leçon ;
- les compétences associées ;
- ce qu'il maîtrise déjà ;
- ce qu'il ne maîtrise pas ;
- les erreurs qu'il répète ;
- la manière dont il apprend le mieux ;
- le temps disponible ;
- les échéances éventuelles ;
- la difficulté des exercices précédents.

À partir de ces informations, l'IA doit décider comment faire travailler l'enfant.

## 2. Objectif principal

Transformer une leçon réelle de l'enfant en un parcours pédagogique personnalisé.

Exemple : l'enfant photographie une leçon sur les planètes. L'application doit pouvoir :

1. reconnaître la matière ;
2. reconnaître le niveau scolaire ;
3. lire la leçon ;
4. identifier les notions importantes ;
5. identifier les compétences travaillées ;
6. construire une représentation structurée de la connaissance ;
7. déterminer les différents niveaux de difficulté ;
8. proposer une première activité ;
9. analyser les réponses ;
10. détecter les erreurs ;
11. adapter les activités suivantes ;
12. faire travailler plusieurs formes de mémorisation ;
13. vérifier la compréhension ;
14. programmer une révision ultérieure ;
15. informer le parent de la progression.

L'enfant ne doit pas avoir à choisir lui-même « Dois-je faire un QCM, des flashcards ou un exercice ? ». L'IA doit décider ce qui est pédagogiquement pertinent.

## 3. Positionnement du produit

L'application se situe entre : application de révision ; jeu éducatif ; professeur particulier numérique ; assistant aux devoirs ; outil de mémorisation ; plateforme de suivi parental.

Elle ne doit pas être conçue comme un simple « ChatGPT pour enfants ». Le cœur du produit est le moteur pédagogique.

## 4. Public cible

### 4.1 Cible principale

Enfants de l'école primaire jusqu'au collège : CP → 3e, soit environ 6 à 15 ans.

Le moteur pédagogique doit cependant pouvoir évoluer vers : maternelle ; lycée ; enseignement spécialisé ; apprentissage des langues.

## 5. Deux espaces distincts

### 5.1 Espace Parent

Le parent peut : créer son compte ; créer plusieurs enfants ; consulter les progrès ; ajouter des objectifs ; renseigner une date de contrôle ; définir un temps de travail ; consulter les difficultés ; consulter l'historique ; obtenir des recommandations ; gérer les paramètres.

### 5.2 Espace Enfant

L'enfant dispose d'une interface simple, ludique, adaptée à son âge, sans surcharge d'informations, centrée sur l'activité. L'enfant ne doit pas être confronté à des tableaux de statistiques complexes.

## 6. Famille et association parent / enfant

### 6.1 Création du compte parent

Le parent crée : compte ; prénom ; éventuellement nom ; adresse e-mail ; mot de passe ou authentification sécurisée.

### 6.2 Création d'un enfant

Le parent peut créer plusieurs profils (exemple : Emma — CM1 ; Lucas — CE1). Chaque enfant possède un environnement totalement indépendant.

### 6.3 Code de liaison

Lors de la création du profil, l'application génère un code temporaire (exemple : 482 731). Le parent peut également générer un QR Code.

### 6.4 Connexion enfant

Sur le téléphone ou la tablette de l'enfant : « J'ai déjà un compte », puis « Entrer le code » ou « Scanner le QR Code ». L'enfant est alors associé au bon profil.

### 6.5 Séparation stricte

Chaque enfant possède ses propres cours, leçons, résultats, compétences, erreurs, progression, badges, historique, plan de révision. Aucune donnée ne doit être mélangée entre frères et sœurs.

## 7. Parcours utilisateur global

### 7.1 Parcours principal

```
Parent → Création enfant → Code / QR → Enfant → Photographie de la leçon → Analyse IA
→ Compréhension de la leçon → Extraction des connaissances → Identification des compétences
→ Construction du parcours → Première activité → Réponse enfant → Analyse → Adaptation
→ Activité suivante → Évaluation → Progression → Révision programmée → Parent informé
```

## 8. Import des leçons

L'application doit accepter plusieurs sources.

- **8.1 Appareil photo** (fonction principale) : cahier, livre, fiche, feuille, tableau, exercice.
- **8.2 Galerie** : importer une photographie existante.
- **8.3 Plusieurs pages** : « Ajouter une page » (page 1, 2, 3, 4…) ; l'IA reconstruit une seule leçon cohérente.
- **8.4 PDF** (V1.5) : PDF scolaire, fiche de cours, document envoyé par un professeur.
- **8.5 Texte** : copier/coller, saisir une leçon, importer un document.

## 9. Reconnaissance intelligente

L'IA doit utiliser OCR, analyse d'image, vision multimodale, compréhension linguistique. Elle doit pouvoir reconnaître : texte, titres, tableaux, schémas, graphiques, cartes, images, formules, annotations, couleurs, éléments manuscrits.

## 10. Gestion des erreurs OCR

Point essentiel. L'IA ne doit jamais inventer silencieusement une information lorsqu'elle n'est pas sûre.

Exemple : « Je ne suis pas certaine d'avoir correctement lu cette phrase. » puis « Peux-tu vérifier ? ». L'application peut zoomer automatiquement sur la zone concernée.

## 11. Analyse pédagogique de la leçon

Après OCR, l'IA transforme la leçon en structure pédagogique. Elle identifie :

- **Informations générales** : matière ; niveau ; chapitre ; titre ; thème ; sous-thèmes.
- **Connaissances** : définitions ; faits ; dates ; personnages ; lieux ; vocabulaire ; règles ; formules ; propriétés ; relations entre concepts.
- **Compétences** — en mathématiques : reconnaître une fraction ; comparer deux fractions ; effectuer une opération ; résoudre un problème ; expliquer une méthode. En français : identifier un verbe ; conjuguer ; accorder ; reconnaître un complément ; appliquer une règle d'orthographe.

## 12. Modèle de connaissance

Le texte brut ne doit pas être transmis directement à un générateur de questions. Il doit d'abord devenir une représentation structurée.

```json
{
  "lesson": {"subject": "science", "grade": "CM1", "title": "Les planètes"},
  "knowledge": [
    {"id": "K001", "concept": "Système solaire", "type": "definition", "importance": 5},
    {"id": "K002", "concept": "Ordre des planètes", "type": "sequence", "importance": 5}
  ]
}
```

Cette structure devient la base du moteur pédagogique.

## 13. Cadre de compétences

L'application ne doit pas uniquement stocker « Score = 83 % ». Elle doit savoir ce que l'enfant sait réellement faire. Chaque notion est associée à une compétence.

Exemple, fractions : reconnaître ; lire ; représenter ; comparer ; calculer ; appliquer dans un problème ; expliquer.

## 14. Modèle de maîtrise

Chaque compétence peut évoluer selon plusieurs niveaux :

| Niveau | Signification |
|---|---|
| 0 | Jamais rencontrée |
| 1 | Découverte |
| 2 | Fragile |
| 3 | En cours d'acquisition |
| 4 | Maîtrisée |
| 5 | Très bien maîtrisée |

Mais le niveau ne doit pas être déterminé uniquement par une série de QCM.

## 15. Mémorisation vs compréhension

Élément central du produit. L'application doit distinguer :

1. **Reconnaissance** — « Quelle est la bonne réponse ? »
2. **Rappel** — « Donne la réponse sans choix. »
3. **Application** — « Utilise cette règle dans un nouvel exercice. »
4. **Explication** — « Explique pourquoi. »
5. **Transfert** — « Utilise ce que tu as appris dans une situation différente. »

Un enfant qui répond correctement à cinq QCM ne doit donc pas automatiquement être considéré comme ayant parfaitement compris.

## 16. Moteur pédagogique

Le moteur doit décider dynamiquement : quelle activité proposer ; quelle difficulté ; quelle notion ; quel format ; combien de questions ; quand changer d'activité ; quand revenir sur une notion ; quand programmer une révision.

## 17. Catalogue d'activités

L'architecture doit être extensible. Chaque activité possède : type ; difficulté ; compétences visées ; notions utilisées ; durée estimée ; critères de réussite ; méthode d'évaluation.

## 18. Activités de mémorisation

- **QCM** : une ou plusieurs réponses.
- **Vrai / Faux** : simple et rapide.
- **Flashcards** : recto « Question », verso « Réponse ».
- **Questions ouvertes** : l'enfant écrit lui-même.
- **Texte à trous** : compléter une phrase.
- **Association** : terme ↔ définition ; personnage ↔ événement ; date ↔ événement.
- **Memory** : retrouver les paires.
- **Classement** : mettre les éléments dans le bon ordre.

## 19. Activités de pratique

Selon la matière : calcul ; conjugaison ; grammaire ; orthographe ; vocabulaire ; dictée ; transformation de phrases ; résolution de problèmes ; classement ; classification ; exercices progressifs.

## 20. Activités visuelles

L'application doit exploiter le potentiel graphique du téléphone ou de la tablette.

- **Coloriage pédagogique** — exemple, leçon sur les animaux : « Colorie uniquement les mammifères. » Le coloriage devient un exercice.
- Schéma à compléter ; image à annoter ; éléments à déplacer ; diagramme ; carte à compléter.

## 21. Géographie

Placer une ville ; placer un pays ; identifier une frontière ; colorier une région ; associer capitale/pays ; placer un fleuve ; reconnaître un relief ; compléter une carte.

## 22. Histoire

Frise chronologique ; replacer un événement ; associer personnage/événement ; date/événement ; remettre une succession dans l'ordre ; cartes historiques ; questions contextualisées ; mise en situation.

## 23. Sciences

Schéma à compléter ; cycle à remettre dans l'ordre ; classification ; expérience virtuelle ; association ; identification ; manipulation d'éléments.

## 24. Mathématiques

L'enfant peut répondre, écrire une opération, utiliser une zone manuscrite, dessiner, poser une opération, résoudre un problème.

L'IA doit idéalement pouvoir analyser le résultat ET la méthode. Exemple : l'enfant trouve 42 alors que la bonne réponse est 48. L'application doit essayer de comprendre : erreur de calcul ? mauvaise méthode ? mauvaise compréhension de l'énoncé ?

## 25. Français

Dictée ; conjugaison ; grammaire ; orthographe ; vocabulaire ; lecture ; compréhension ; transformation de phrases ; phrases à compléter ; identification grammaticale.

## 26. Activités orales

Fonction importante mais pouvant arriver après le MVP. L'enfant peut parler avec l'IA (« Explique-moi ce qu'est une planète. »). L'IA écoute et analyse : présence des notions importantes ; compréhension ; erreurs ; vocabulaire ; cohérence. Elle peut ensuite demander : « Et pourquoi la Terre est-elle différente de Jupiter ? »

## 27. Mode « Je n'ai pas compris »

L'enfant dispose toujours d'un bouton « ❓ Je n'ai pas compris ». L'aide doit être progressive :

1. Indice.
2. Petit rappel.
3. Exemple similaire.
4. Explication étape par étape.
5. Solution complète.

L'objectif est de ne pas donner immédiatement la réponse.

## 28. Explication adaptée à l'âge

L'IA adapte automatiquement son langage (« Explique-moi comme si j'avais 7 ans », ou automatiquement selon l'âge). Un élève de CP ne doit pas recevoir la même explication qu'un élève de 3e.

## 29. Mode devoirs

Il doit être séparé du mode révision. Objectif : aider l'enfant à résoudre son exercice sans faire le travail à sa place.

Exemple, énoncé « Paul possède 24 billes… » : « Qu'est-ce qu'on cherche ? » → « Quelle opération pourrait-on utiliser ? » → « Pourquoi ? » → « Fais le calcul. » → « Vérifions ensemble. »

## 30. Mode révision

Objectif : apprendre + mémoriser + comprendre + consolider. Le moteur peut utiliser toutes les activités disponibles.

## 31. Planification du temps

Le parent peut définir « 10 minutes par jour ». L'IA construit automatiquement une séance de 10 minutes. Elle peut également fonctionner avec 5, 10, 15, 20 ou 30 minutes.

La séance doit être dynamique : si l'enfant maîtrise rapidement → difficulté supérieure ; si l'enfant rencontre des difficultés → activité différente ou aide.

## 32. Détection de fatigue / désengagement

Sans diagnostic psychologique. L'application peut observer : réponses extrêmement rapides ; erreurs répétées ; abandons ; temps de réponse qui augmente ; répétition des mêmes erreurs ; changement brutal de comportement.

Elle peut proposer : « On fait une petite pause ? » ou « Essayons une activité différente. »

## 33. Plan de révision intelligent

Le parent peut indiquer « Contrôle de maths vendredi ». L'IA construit automatiquement : lundi, découverte / diagnostic ; mardi, exercices ciblés ; mercredi, mémorisation ; jeudi, révision des erreurs ; vendredi, mini-évaluation. Le système doit pouvoir modifier le planning selon les résultats.

## 34. Répétition espacée

Les notions fragiles doivent revenir régulièrement. Une notion correctement maîtrisée aujourd'hui ne doit pas disparaître du système.

Exemple : J0 découverte ; J1 rappel ; J3 exercice ; J7 rappel ; J14 contrôle. Les intervalles doivent évoluer selon la réussite.

## 35. Adaptation en temps réel

Exemple : l'enfant échoue deux fois sur « accord sujet/verbe ». L'application peut interrompre l'activité prévue et proposer :

1. rappel de règle ;
2. exemple simple ;
3. exercice très facile ;
4. exercice normal ;
5. retour à l'activité initiale.

## 36. Difficulté dynamique

Chaque activité peut posséder plusieurs niveaux (facile, normal, difficile, expert). Mais la difficulté doit aussi être calculée automatiquement. Elle dépend de : historique ; erreurs ; vitesse ; type de compétence ; difficulté de la notion ; réussite récente.

## 37. Mission pédagogique

Au lieu d'une simple liste d'exercices, l'application peut construire une mission. Exemple, 🚀 Mission : Les planètes — étape 1, colorier les planètes telluriques ; étape 2, remettre les planètes dans l'ordre ; étape 3, flashcards ; étape 4, quiz ; étape 5, expliquer oralement ; étape 6, challenge final. Cela crée une progression narrative.

## 38. Gamification

Le système peut utiliser : XP ; niveaux ; badges ; séries ; missions ; défis ; objectifs ; récompenses.

## 39. Philosophie de la gamification

Il faut éviter « Tu es mauvais parce que tu as fait 40 %. » Les récompenses doivent valoriser : effort ; progression ; persévérance ; amélioration ; régularité ; compréhension.

Exemple : « 🏆 Tu as réussi une notion qui te posait problème hier ! » plutôt que simplement « 10/10 ».

## 40. Tableau de bord enfant

Il doit rester simple :

```
👋 Bonjour Emma !
🚀 Mission du jour : Les fractions
⭐ 120 XP
🔥 Série : 4 jours
🎯 Objectif : Maîtriser les fractions
[ COMMENCER ]
```

Pas de tableau complexe.

## 41. Tableau de bord parent

```
Emma — CM1
Cette semaine : 4 séances, 37 minutes

Français       🟢 86 %
Mathématiques  🟠 72 %
Histoire       🟢 91 %

À renforcer :
🔴 Comparaison de fractions
🟠 Imparfait

Progression : ↗ +8 % cette semaine
```

## 42. Statuts pédagogiques

Le parent doit pouvoir comprendre immédiatement : 🟢 Maîtrisé ; 🟠 En cours d'acquisition ; 🔴 À renforcer. Ces statuts doivent être associés à des explications.

## 43. Analyse des erreurs

Le système doit conserver un historique. Exemple, fractions, 5 erreurs : comparaison ; dénominateur ; représentation graphique. L'IA peut détecter une erreur récurrente : « Emma confond régulièrement numérateur et dénominateur. »

## 44. Historique

Le parent peut consulter : séances ; durée ; matière ; leçon ; activités ; erreurs ; progression.

## 45. Graphiques

Possibilité de visualiser : évolution par matière ; progression d'une compétence ; temps de travail ; fréquence des erreurs ; maîtrise dans le temps.

## 46. Assistant parent

Le parent peut demander « Sur quoi devrait travailler Emma cette semaine ? ». L'IA répond à partir des données réelles : « Les fractions restent la principale notion à renforcer. Je recommande trois courtes séances cette semaine, principalement sur la comparaison puis l'application dans des problèmes. »

Autre question : « Comment puis-je l'aider ? » L'IA propose des actions simples adaptées au niveau de l'enfant.

## 47. Objectifs parents

Le parent peut définir : temps quotidien ; matière prioritaire ; objectif ; date de contrôle ; nombre de séances.

## 48. Notifications

Possibilité future : « Emma n'a pas encore fait sa séance aujourd'hui. » ou « La notion de fractions est à revoir aujourd'hui. » Les notifications doivent rester raisonnables et éviter de créer une pression excessive.

## 49. Architecture technique

```
                APPLICATION MOBILE (Flutter)
                          │
                          ▼
                     API FastAPI
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
      Moteur pédagogique          PostgreSQL
              │
      ┌───────┼────────┐
      ▼       ▼        ▼
     OCR    Vision    LLM
      │
      ▼
Analyse pédagogique → Knowledge Graph / modèle → Génération activité
→ Évaluation → Adaptation → Progression
```

## 50. Application mobile

Technologie recommandée : Flutter / Dart. Avantages : Android ; iOS ; iPadOS ; une base de code ; interface riche ; animations ; caméra ; canvas ; audio ; jeux éducatifs. Android sera développé en premier.

## 51. Backend

Python + FastAPI. Responsabilités : authentification ; utilisateurs ; familles ; enfants ; leçons ; IA ; sessions ; résultats ; progression ; planning ; notifications.

## 52. Base de données

PostgreSQL. Entités principales : User, Parent, Family, Child, Lesson, LessonPage, Knowledge, Concept, Skill, Activity, Question, Answer, Session, SessionStep, Progress, Error, Achievement, Mission, RevisionPlan, Goal, Notification.

## 53. Relations principales

```
Parent
  └── Family
        ├── Child
        │     ├── Lesson ── Knowledge
        │     ├── Session ── Answer
        │     └── Progress
        └── Goals
```

## 54. Objet Child

```json
{"id": "...", "first_name": "Emma", "grade": "CM1", "birth_year": 2016,
 "subjects": [], "preferences": {}, "learning_profile": {}}
```

Le stockage de données personnelles doit être limité au strict nécessaire.

## 55. Objet Lesson

```json
{"id": "...", "child_id": "...", "subject": "mathematics", "grade": "CM1", "title": "Fractions",
 "source": "camera", "pages": [], "analysis_status": "completed"}
```

## 56. Objet Knowledge

```json
{"id": "...", "lesson_id": "...", "concept": "Comparer deux fractions", "type": "skill",
 "importance": 5, "difficulty": 3}
```

## 57. Objet Activity

```json
{"type": "FILL_BLANK", "skill_id": "...", "difficulty": 2, "estimated_duration": 90, "content": {}}
```

Types possibles : MCQ, TRUE_FALSE, FLASHCARD, FILL_BLANK, MATCH, ORDER, MEMORY, OPEN_QUESTION, CALCULATION, DICTATION, DRAW, COLORING, MAP, TIMELINE, DRAG_DROP, ORAL, PROBLEM, PUZZLE.

## 58. API principale

```
POST /auth/register                POST /auth/login
POST /families                     GET  /families
POST /children                     GET  /children
POST /children/{id}/link-code      POST /children/link
POST /lessons                      POST /lessons/{id}/analyze
GET  /lessons/{id}
POST /sessions                     GET  /sessions/{id}
POST /activities/generate          POST /answers
GET  /children/{id}/progress       GET  /children/{id}/skills
GET  /children/{id}/errors
POST /revision-plans               GET  /revision-plans
GET  /parent/dashboard
```

## 59. Orchestrateur IA

L'IA ne doit pas être un seul appel gigantesque. Architecture recommandée — AI Orchestrator : OCR Agent ; Lesson Understanding ; Knowledge Extraction ; Curriculum Mapping ; Activity Generator ; Answer Evaluator ; Error Analyzer ; Pedagogical Planner ; Adaptive Engine ; Explanation Engine ; Revision Planner ; Parent Assistant.

## 60. Fournisseur IA

L'architecture doit rester indépendante du fournisseur. Éviter de construire toute l'application autour d'un seul modèle. Créer une couche AIProvider permettant de changer de modèle ultérieurement.

## 61. Contrats JSON

Les appels IA doivent retourner des structures strictes, par exemple :

```json
{"subject": "history", "grade": "CM1",
 "concepts": [{"name": "Révolution française", "importance": 5,
               "skills": ["identifier la date", "identifier les événements"]}]}
```

Cela évite de dépendre de réponses textuelles imprévisibles.

## 62. Système d'évaluation

Chaque réponse doit générer : correct / incorrect ; confidence ; skill ; concept ; difficulty ; response_time ; hint_used ; attempt_count ; error_type.

## 63. Types d'erreurs

Erreur de connaissance ; erreur de calcul ; mauvaise méthode ; mauvaise lecture ; confusion de concepts ; oubli ; imprécision ; réponse aléatoire ; mauvaise compréhension de l'énoncé.

## 64. Moteur de progression

Le score doit combiner : réussite ; répétition ; difficulté ; ancienneté ; type d'exercice ; autonomie ; besoin d'aide ; compréhension.

## 65. Transfert des compétences

Une compétence considérée comme maîtrisée doit être testée dans plusieurs contextes. Exemple, fraction : reconnaître ; lire ; comparer ; calculer ; résoudre un problème ; expliquer. Ce n'est qu'après validation de plusieurs dimensions que la compétence peut passer à 🟢 Maîtrisée.

## 66. Moteur de recommandation

Chaque fin de session doit déterminer : à revoir maintenant ; à revoir demain ; à revoir dans 3 jours ; maîtrisé. Le moteur peut également choisir une nouvelle activité plutôt que le même exercice.

## 67. Génération de questions

Les questions doivent être : directement liées à la leçon ; adaptées à l'âge ; adaptées au niveau ; différentes les unes des autres ; pédagogiquement pertinentes ; contrôlées contre les erreurs factuelles. Éviter les questions artificielles simplement générées pour remplir un quota.

## 68. Contrôle de qualité IA

Avant présentation à l'enfant :

1. vérifier que la question correspond à la leçon ;
2. vérifier la bonne réponse ;
3. vérifier qu'il n'y a pas plusieurs bonnes réponses involontaires ;
4. vérifier le niveau ;
5. vérifier le vocabulaire ;
6. vérifier la cohérence.

## 69. Sécurité

L'application concerne des mineurs ; la sécurité doit être conçue dès le début. Principes : authentification sécurisée ; chiffrement ; séparation parent/enfant ; contrôle des accès ; suppression des données ; minimisation des données ; logs sécurisés ; limitation des données envoyées aux modèles IA.

## 70. RGPD

Le produit devra prévoir notamment : information claire du parent ; consentement approprié ; droit d'accès ; droit de rectification ; droit à l'effacement ; export des données ; politique de conservation ; gestion des données de mineurs ; sous-traitants IA ; hébergement adapté. Une analyse juridique spécialisée devra être réalisée avant commercialisation.

## 71. Photos des leçons

Il faut définir une politique de conservation. Possibilités : **mode temporaire**, photo conservée uniquement pour l'analyse ; **mode historique**, photo conservée avec la leçon. Le parent doit pouvoir contrôler cette conservation.

## 72. Données vocales

Pour le mode oral : information du parent ; durée de conservation définie ; possibilité de suppression ; traitement sécurisé.

## 73. Publicité

Éviter totalement les publicités ciblées dans l'espace enfant. Le modèle économique doit être compatible avec une expérience éducative saine.

## 74. Accessibilité

Prévoir : taille de texte adaptable ; contraste ; lecture audio ; navigation simple ; commandes vocales ; alternatives visuelles ; animations désactivables.

## 75. Design enfant

Grandes zones tactiles ; peu de texte ; illustrations ; animations ; feedback immédiat ; progression visible ; erreurs présentées sans culpabilisation.

## 76. Design parent

Plus sobre. Informations importantes : Comment va mon enfant ? Que maîtrise-t-il ? Que doit-il renforcer ? Que faire cette semaine ?

## 77. Écrans V1

1. Choix Parent / Enfant.
2. Connexion / création de compte.
3. Création enfant.
4. Code / QR.
5. Dashboard parent.
6. Dashboard enfant.
7. Ajouter une leçon.
8. Caméra.
9. Validation des pages.
10. Analyse IA.
11. Leçon comprise.
12. Première activité.
13. Réponse.
14. Correction.
15. Aide.
16. Activité suivante.
17. Résultat de séance.
18. Progression.
19. Historique.

## 78. Écrans V2

Missions ; XP ; badges ; memory ; coloriage ; cartes ; frises ; puzzles ; drag & drop ; défis.

## 79. Écrans V3

Planification ; répétition espacée ; recommandations ; adaptation avancée ; compétences ; analyse d'erreurs ; objectifs.

## 80. Écrans V4

Conversation vocale ; lecture ; oral ; explication de leçon ; professeur IA.

## 81. Écrans parent avancés

Accueil → Mes enfants ; Progression ; Matières ; Compétences ; Difficultés ; Planning ; Objectifs ; Historique ; Recommandations IA ; Paramètres.

## 82. Profil d'apprentissage

Le système peut progressivement apprendre : activités efficaces ; types d'erreurs ; rythme ; niveau ; durée optimale ; préférences d'apprentissage.

Attention : le système ne doit pas enfermer l'enfant dans une catégorie définitive du type « Cet enfant est visuel ». Il s'agit plutôt d'observer ce qui fonctionne dans certaines situations.

## 83. Mode « Enseigne-moi »

L'enfant devient professeur : « Explique-moi les fractions comme si j'étais ton élève. » L'IA joue l'élève et pose des questions. Cela permet d'évaluer la compréhension profonde.

## 84. Mode jeu de rôle

L'enfant peut devenir professeur, astronaute, explorateur, scientifique, détective, historien, journaliste. Le contenu pédagogique reste néanmoins contrôlé. Exemple : « Tu es un explorateur qui doit traverser la France. Place correctement les régions pour continuer ton voyage. »

## 85. Univers de progression

À terme, l'enfant pourrait construire progressivement une planète, une ville, un laboratoire, un musée, une base spatiale. Les progrès scolaires débloquent des éléments. La gamification reste secondaire par rapport à l'apprentissage.

## 86. Rapport de fin de session

```
🎉 Séance terminée !
Durée : 11 min
Aujourd'hui : 🟢 Les nombres décimaux · 🟢 Addition · 🟠 Comparaison
À revoir : Comparer deux nombres décimaux
Prochaine révision : Demain
XP : +35
```

## 87. Rapport parent

« Emma a travaillé 11 minutes aujourd'hui. Elle progresse bien sur les nombres décimaux. Une difficulté persiste sur la comparaison. L'application recommande une courte séance demain, puis une vérification dans 3 jours. »

## 88. Mode hors connexion

À étudier pour certaines fonctionnalités. Possible : consulter les leçons ; effectuer certaines activités déjà téléchargées ; enregistrer les réponses ; synchroniser plus tard. L'analyse IA nécessitera probablement une connexion dans la première version.

## 89. Performance

Lancement rapide ; caméra réactive ; animations fluides ; faible consommation ; gestion correcte des téléphones Android modestes. Les activités simples doivent rester fonctionnelles même avec une connexion moyenne.

## 90. Observabilité

Le backend doit suivre : erreurs API ; temps de réponse ; erreurs IA ; taux d'abandon ; consommation IA ; coûts par session ; problèmes de génération.

## 91. Maîtrise des coûts IA

Point critique du projet. Éviter d'envoyer inutilement toute la conversation, toutes les photos, tout l'historique. Utiliser : données structurées ; résumés ; cache ; modèles adaptés à chaque tâche ; traitement local quand possible.

## 92. Architecture évolutive

Le système doit permettre plus tard : plusieurs fournisseurs IA ; modèles spécialisés ; OCR local ; IA locale ; moteur pédagogique indépendant du LLM. Le LLM doit être un composant du système, pas le système entier.

## 93. Tests

- **Fonctionnels** : inscription ; création enfant ; liaison ; photo ; analyse ; activité ; réponse ; correction ; progression.
- **IA** : OCR ; extraction ; génération ; correction ; adaptation.
- **Pédagogiques** : cohérence ; niveau ; difficulté ; absence de questions hors sujet ; progression.

## 94. Tests utilisateurs

Faire tester avec : parents ; enfants CP ; enfants CE ; enfants CM ; collégiens. Observer : compréhension ; facilité d'utilisation ; motivation ; confusion ; durée des séances.

## 95. MVP

Le MVP doit rester raisonnable. Fonctionnalités obligatoires :

- **Parent** : création compte ; création enfant ; code/QR ; dashboard simple.
- **Enfant** : connexion ; photo ; analyse ; première leçon ; QCM ; vrai/faux ; flashcards ; questions ; correction ; aide.
- **IA** : OCR ; compréhension ; extraction des connaissances ; génération ; correction ; adaptation simple.
- **Progression** : compétences ; maîtrise ; historique ; erreurs.

## 96. Ce qui ne doit pas être dans le premier MVP

École/ENT ; univers 3D ; jeu complexe ; monde virtuel ; reconnaissance vocale avancée ; professeur vocal temps réel ; synchronisation complexe ; marketplace ; réseau social.

## 97. V0 — Prototype

Objectif : prouver que le concept fonctionne. Photo → OCR / Vision → Analyse → Structure de connaissances → Quiz → Correction → Résultat. Une seule matière peut suffire.

## 98. V1 — Application utilisable

Parent ; enfant ; plusieurs enfants ; QR/code ; leçons ; activités ; progression ; compétences ; historique ; adaptation simple.

## 99. V2 — Application ludique

Missions ; XP ; badges ; memory ; puzzles ; coloriage ; cartes ; frises ; drag & drop.

## 100. V3 — Véritable moteur pédagogique

Répétition espacée ; difficulté dynamique ; compréhension profonde ; transfert ; analyse d'erreurs ; planning ; test à venir ; recommandations ; adaptation avancée. Cette version constitue véritablement le cœur différenciant du produit.

## 101. V4 — Professeur IA

Voix ; conversation ; lecture ; questions ouvertes ; explication orale ; évaluation orale ; dialogue pédagogique.

## 102. V5 — Écosystème parent

Objectifs ; calendrier ; rapports hebdomadaires ; recommandations ; notifications ; assistant parent ; plusieurs enfants ; suivi long terme.

## 103. V6 — iOS / iPadOS

iPhone ; iPad ; synchronisation ; notifications ; caméra ; optimisation Apple ; App Store. Flutter permettra de limiter la duplication du développement.

## 104. Évolution vers l'école

À plus long terme : ENT ; enseignants ; import de devoirs ; cahier de textes ; programmes officiels ; compétences ; classes. Cela ne doit pas bloquer la première version.

## 105. Programmes scolaires

Le moteur pédagogique doit progressivement intégrer un référentiel : Niveau → Matière → Domaine → Compétence → Sous-compétence → Notion. Cela permettra de savoir non seulement « Emma a réussi 85 % », mais « Emma maîtrise telle compétence de CM1 mais rencontre encore des difficultés sur telle sous-compétence ».

## 106. Architecture pédagogique finale

```
LEÇON → OCR / VISION / IMPORT → COMPRÉHENSION DU CONTENU → STRUCTURATION DES SAVOIRS
→ RÉFÉRENTIEL COMPÉTENCES → PROFIL DE L'ENFANT → MOTEUR PÉDAGOGIQUE
→ (MÉMOIRE | COMPRÉHENSION | PRATIQUE) → ACTIVITÉ → RÉPONSE → ANALYSE D'ERREUR
→ MISE À JOUR MAÎTRISE → CHOIX ACTIVITÉ SUIVANTE → RÉPÉTITION ESPACÉE
→ PROGRESSION ENFANT → RECOMMANDATION PARENT
```

## 107. Différenciation du produit

1. Comprendre réellement la leçon, et pas uniquement extraire du texte.
2. Construire une représentation pédagogique, et pas uniquement un résumé.
3. Connaître l'enfant : historique, erreurs, progression.
4. Choisir la bonne pédagogie, et pas uniquement générer des QCM.
5. Distinguer mémorisation et compréhension.
6. Adapter en temps réel.
7. Répéter au bon moment.
8. Utiliser des activités très différentes.
9. Donner une vision utile au parent.
10. Aider sans faire les devoirs à la place de l'enfant.

## 108. Principes absolus du produit

1. L'IA doit enseigner, pas seulement générer.
2. Une erreur est une information pédagogique.
3. Une bonne note ne signifie pas nécessairement une bonne compréhension.
4. L'activité doit s'adapter à l'enfant.
5. L'enfant ne doit pas avoir besoin de comprendre la pédagogie.
6. Le parent doit comprendre rapidement où en est son enfant.
7. L'application doit favoriser l'autonomie.
8. L'application doit être ludique sans transformer l'apprentissage en compétition.
9. La sécurité des données des enfants est une priorité dès la conception.
10. Le moteur pédagogique doit rester indépendant du fournisseur d'IA.

## 109. Vision finale

L'enfant pose son téléphone devant son cahier. Il photographie sa leçon. Quelques secondes plus tard : « J'ai compris ta leçon. »

L'application sait ce que contient la leçon, ce qui est important, ce qui doit être mémorisé, ce qui doit être compris, quelles compétences sont travaillées, ce que l'enfant connaît déjà, ce qu'il oublie régulièrement.

Elle lui propose alors une véritable séance : « Aujourd'hui, on va faire une mission de 10 minutes. » Pendant la séance, l'IA observe les réponses et adapte son comportement. Si l'enfant comprend → elle augmente la difficulté. S'il bloque → elle simplifie. S'il mémorise mais ne comprend pas → elle change de type d'exercice. S'il fait toujours la même erreur → elle travaille spécifiquement cette erreur. S'il maîtrise → elle programme une révision future. À la fin : « Bravo, tu as vraiment progressé sur cette notion. »

Et le parent reçoit une information simple : « Emma maîtrise maintenant les fractions simples. Elle doit encore travailler la comparaison de fractions. Une courte séance de 10 minutes demain est recommandée. »

L'application devient ainsi progressivement un tuteur scolaire personnel, capable d'accompagner l'enfant sur la durée et de faire évoluer son enseignement en fonction de ses progrès.

## 110. Ordre de développement recommandé

1. Architecture technique.
2. Authentification parent.
3. Création enfants.
4. Code / QR de liaison.
5. Capture/import d'une leçon.
6. Pipeline OCR + IA.
7. Structure de connaissances.
8. Premier moteur de génération d'activités.
9. QCM / Vrai-Faux / Flashcards / Questions.
10. Évaluation des réponses.
11. Système de compétences et maîtrise.
12. Dashboard enfant.
13. Dashboard parent.
14. Adaptation dynamique.
15. Répétition espacée.
16. Missions et gamification.
17. Activités graphiques.
18. Mode devoirs.
19. Planification des contrôles.
20. Voix et professeur IA.
21. iOS / iPadOS.
22. Éventuelle intégration scolaire.

## 111. Conclusion

Le produit ne doit donc pas être développé comme « une application qui transforme une photo en quiz », mais comme « une plateforme d'apprentissage personnalisée qui transforme n'importe quelle leçon en parcours pédagogique adaptatif ».

La photographie n'est que la porte d'entrée. Le véritable produit est constitué de quatre briques : **COMPRENDRE + ENSEIGNER + S'ADAPTER + SUIVRE LA PROGRESSION**.

Le cœur technologique sera le moteur pédagogique adaptatif, tandis que l'IA multimodale permettra de comprendre les supports scolaires et de générer les contenus nécessaires.

Le résultat recherché est une expérience qui donne à l'enfant l'impression d'avoir son propre professeur particulier numérique, tout en donnant au parent une vision claire, rassurante et exploitable de sa progression.

---

> **§112 à 149** — ajoutés en version 1.1 par le porteur du projet : les règles de comportement de l'IA, les
> contrats entre composants, les garde-fous, les états du système, la gestion des incertitudes et
> les règles de décision. État de l'existant au regard de chaque règle :
> [`specification-technique.md`](specification-technique.md) §11.

## 112. Directives pour l'IA de développement

Cette section définit les règles que toute IA utilisée pour concevoir, développer, modifier, tester ou maintenir l'application doit respecter.

L'IA de développement ne doit pas considérer le projet comme une simple application CRUD avec quelques appels à un LLM. Le produit est avant tout un système pédagogique adaptatif, dont l'IA générative constitue un composant.

L'architecture, le code et les données doivent donc préserver cette séparation :

```
APPLICATION → MOTEUR PÉDAGOGIQUE → SERVICES IA
```

et non :

```
APPLICATION → LLM → réponse
```

### 112.1 Règle fondamentale

L'IA ne doit jamais prendre une décision pédagogique importante uniquement sur la base d'une génération libre du LLM.

Toute décision importante doit pouvoir être représentée par des données structurées, expliquée, enregistrée, reproduite, testée et modifiée indépendamment du modèle IA.

Exemples : niveau de maîtrise, compétence acquise, erreur détectée, difficulté suivante, choix de l'activité, date de prochaine révision, validation d'une réponse, progression d'une compétence.

**Le LLM peut proposer une analyse. Le moteur pédagogique décide.**

## 113. Architecture de décision IA

Le système doit fonctionner selon une architecture en plusieurs étapes :

```
ENTRÉE → Compréhension → Structuration → Validation → État actuel de l'enfant
→ Moteur pédagogique → Décision → Génération de contenu → Validation automatique
→ Présentation à l'enfant → Réponse → Évaluation → Mise à jour du profil → Nouvelle décision
```

Une génération IA qui échoue ou produit une donnée incohérente ne doit jamais pouvoir contaminer directement la progression de l'enfant.

## 114. État pédagogique de l'enfant

Le système doit conserver un état pédagogique structuré. Exemple :

```json
{
  "child_id": "child_001",
  "skill_id": "fractions_compare",
  "mastery": 2.7,
  "confidence": 0.81,
  "recent_success_rate": 0.68,
  "recognition": 0.90,
  "recall": 0.62,
  "application": 0.55,
  "explanation": 0.40,
  "transfer": 0.30,
  "independence": 0.72,
  "last_seen": "2026-09-24T17:30:00",
  "next_review": "2026-09-27T17:30:00",
  "error_patterns": ["denominator_confusion"]
}
```

Cette structure permet de distinguer ce que l'enfant reconnaît, mémorise, sait appliquer, sait expliquer, sait transférer et sait faire seul. Un score global ne doit jamais remplacer ces informations.

## 115. Niveau de confiance

Chaque analyse IA importante doit comporter un niveau de confiance :

```json
{ "result": "...", "confidence": 0.91, "needs_human_confirmation": false }
```

Le niveau de confiance décide du comportement :

- **confiance élevée** : le système peut continuer automatiquement ;
- **confiance moyenne** : le système peut demander une vérification ou utiliser une seconde analyse ;
- **confiance faible** : le système ne doit pas inventer ; il demande une confirmation (« Je pense avoir lu “1789”, mais je ne suis pas certaine. Peux-tu vérifier ? »).

## 116. Principe anti-hallucination

L'IA ne doit jamais présenter comme provenant de la leçon une information qui n'y est pas, sauf si elle est explicitement identifiée comme un apport externe.

Chaque connaissance extraite doit pouvoir être reliée à sa source :

```json
{
  "concept": "Révolution française",
  "source": { "lesson_id": "lesson_001", "page": 2, "text_reference": "..." }
}
```

Cela permet de répondre à la question : « Pourquoi l'application pense-t-elle que cette notion fait partie de ma leçon ? »

## 117. Source de vérité

Le système doit distinguer plusieurs sources : `SOURCE_LESSON`, `SOURCE_CURRICULUM`, `SOURCE_CHILD_HISTORY`, `SOURCE_PARENT`, `SOURCE_AI_INFERENCE`, `SOURCE_EXTERNAL_KNOWLEDGE`.

Une information issue d'une inférence IA ne doit pas être considérée comme équivalente à une information explicitement présente dans le document scolaire.

## 118. Pipeline de génération d'activité

Une activité ne doit jamais être générée directement à partir d'une simple instruction (« Génère 10 questions sur cette leçon »). Le processus attendu est :

```
Leçon → Connaissances → Compétences → État de maîtrise → Objectif pédagogique
→ Type d'activité → Difficulté → Génération → Validation → Présentation
```

Le générateur reçoit une spécification, par exemple :

```json
{
  "objective": "application",
  "skill": "compare_fractions",
  "current_mastery": 2.4,
  "target_mastery": 3,
  "activity_type": "PROBLEM",
  "difficulty": 2,
  "estimated_duration": 120
}
```

## 119. Validation en deux étapes

Toute activité générée doit être contrôlée avant d'être présentée à l'enfant.

- **Validation structurelle** : JSON valide, champs obligatoires, réponse présente, compétence existante, difficulté valide, durée cohérente, type d'activité autorisé.
- **Validation pédagogique** : correspondance avec la leçon, niveau scolaire, difficulté, absence d'ambiguïté, absence de double réponse, vocabulaire adapté, exactitude, absence d'informations inventées, cohérence de la correction.

Si une validation échoue : génération → validation → échec → régénération → validation. Après plusieurs échecs, le système utilise une activité de secours prédéfinie.

## 120. Activités de secours

Le système ne doit jamais se retrouver sans activité parce que le LLM est indisponible ou qu'une génération échoue. Chaque compétence importante doit disposer d'activités de secours déterministes lorsque c'est possible :

```
LLM indisponible → activité générée précédemment disponible ? oui → l'utiliser
                                                         non → activité générique compatible avec la compétence
                                                               → si impossible : message utilisateur approprié
```

## 121. Le LLM ne doit pas être nécessaire partout

L'architecture doit identifier pour chaque opération si elle nécessite aucun LLM, un modèle léger, un modèle multimodal, un modèle puissant ou un calcul déterministe.

| Fonction | Technologie privilégiée |
| --- | --- |
| Calcul mathématique | code déterministe |
| Score | code déterministe |
| Temps de réponse | code |
| Progression | moteur pédagogique |
| Répétition espacée | algorithme |
| OCR | OCR spécialisé |
| Analyse d'image | vision |
| Reformulation | LLM |
| Explication | LLM |
| Génération d'exercice | LLM |
| Validation | code + IA |
| Classification de compétence | IA + référentiel |

## 122. Mémoire de l'IA

L'IA ne doit pas recevoir systématiquement tout l'historique de l'enfant. Le système construit un contexte minimal pertinent : âge / niveau, matière, leçon, compétence actuelle, niveau de maîtrise, erreurs pertinentes, activités récentes, objectif actuel, contraintes de séance.

Il évite d'envoyer tout l'historique, toutes les anciennes réponses, toutes les photos, toutes les conversations.

## 123. Personnalisation sans étiquetage

Le système peut apprendre ce qui fonctionne mieux pour l'enfant, mais ne doit pas produire de diagnostic définitif (« Cet enfant est visuel »). Il utilise des observations probabilistes :

```json
{ "visual_activity_success": 0.82, "text_activity_success": 0.61, "oral_activity_success": 0.74 }
```

Il peut alors privilégier certaines approches sans enfermer l'enfant dans une catégorie.

## 124. Moteur pédagogique à états

Une séance est une machine à états :

```
START → DIAGNOSTIC → LEARNING → PRACTICE → EVALUATION → REMEDIATION → TRANSFER → CONSOLIDATION → END
```

Le moteur peut revenir à un état précédent (PRACTICE → échec répété → REMEDIATION → PRACTICE) ou avancer plus vite (EVALUATION → bonne réussite → TRANSFER).

## 125. Règles d'adaptation

Le moteur dispose de règles explicites, par exemple :

- réussite ≥ 85 % **et** autonomie élevée **et** difficulté actuelle faible → augmenter la difficulté ;
- réussite < 50 % → réduire la difficulté ;
- même erreur ≥ 2 fois → déclencher une remédiation ;
- réussite élevée **mais** transfert faible → activité de transfert ;
- reconnaissance élevée **mais** rappel faible → rappel actif ;
- rappel élevé **mais** application faible → exercice d'application ;
- application élevée **mais** explication faible → demander une explication ;
- plusieurs erreurs consécutives → proposer une activité différente.

Ces règles doivent être configurables sans modifier le code principal.

## 126. Raison de chaque décision

Chaque décision pédagogique importante doit pouvoir enregistrer sa justification :

```json
{
  "decision": "REMEDIATION",
  "reason": ["same_error_repeated_3_times", "mastery_below_threshold"],
  "previous_activity": "MCQ",
  "next_activity": "GUIDED_EXERCISE"
}
```

Le parent ou le développeur doit pouvoir comprendre pourquoi le système a changé de stratégie.

## 127. Mode devoirs — garde-fou

Le mode devoirs doit être explicitement différent du mode correction. Le système privilégie :

```
Question → Indice → Question intermédiaire → Rappel de notion → Méthode → Tentative de l'enfant → Correction guidée
```

et évite « énoncé → réponse complète immédiate ». L'objectif est de maximiser l'autonomie de l'enfant.

## 128. Détection d'une réponse aléatoire

Le système doit pouvoir distinguer : erreur réelle, oubli, incompréhension, réponse aléatoire, réponse obtenue avec aide, réponse correcte mais non maîtrisée. Une réponse correcte obtenue après trois indices n'équivaut pas à une réponse correcte spontanée.

## 129. Autonomie

Chaque réussite comporte un indicateur d'autonomie :

```json
{ "correct": true, "hint_used": false, "help_level": 0, "independence": 1.0 }
```

Une réussite avec aide contribue positivement à la progression, mais moins qu'une réussite autonome.

## 130. Évaluation continue

Une compétence n'est jamais considérée comme définitivement acquise : elle peut être oubliée, fragile dans un nouveau contexte, maîtrisée en reconnaissance mais pas en application, ou dans une leçon mais pas dans un problème réel. La maîtrise évolue dans le temps.

## 131. Explications au parent

Les explications destinées aux parents reposent sur les données réelles.

- À éviter : « Emma semble avoir des difficultés en mathématiques. »
- À préférer : « Sur les 8 dernières activités portant sur la comparaison de fractions, Emma a réussi 4 exercices seule, 2 avec un indice et 2 après une explication. La difficulté principale identifiée concerne la comparaison des dénominateurs. »

Le système distingue clairement le **fait observé** de l'**interprétation de l'IA**.

## 132. Interface IA de développement

Lorsqu'une IA de développement travaille sur le projet, elle doit :

1. lire le cahier des charges avant toute modification ;
2. identifier les composants existants ;
3. ne pas recréer une fonctionnalité déjà présente ;
4. vérifier les dépendances ;
5. respecter l'architecture existante ;
6. ne pas modifier arbitrairement les contrats API ;
7. préserver les données existantes ;
8. écrire ou mettre à jour les tests ;
9. vérifier les migrations de base de données ;
10. vérifier les erreurs potentielles avant de considérer une tâche terminée.

## 133. Règle « ne pas casser l'existant »

Avant toute modification : analyser → identifier les dépendances → modifier → tester → vérifier les régressions.

Une fonctionnalité nouvelle ne doit pas casser : authentification, comptes parents, comptes enfants, liaison, leçons, séances, progression, API existantes.

## 134. Mode de travail de l'IA de codage

Pour chaque tâche, l'IA produit avant modification : **objectif, fichiers concernés, impact, plan, risques, tests prévus**. Après modification : **modifications effectuées, tests réalisés, résultats, problèmes restants**.

L'IA ne doit pas prétendre qu'une fonctionnalité fonctionne si elle n'a pas été testée.

## 135. Gestion des erreurs

Toute erreur a un comportement défini. Catégories : `USER_ERROR`, `VALIDATION_ERROR`, `NETWORK_ERROR`, `AUTH_ERROR`, `OCR_ERROR`, `AI_ERROR`, `DATABASE_ERROR`, `TIMEOUT`, `RATE_LIMIT`, `UNKNOWN_ERROR`.

L'utilisateur ne reçoit jamais une erreur technique brute (« 500 Internal Server Error ») : l'interface fournit un message compréhensible.

## 136. Observabilité de l'IA

Chaque appel IA important est tracé avec : provider, model, prompt_version, input_type, latency, token_usage, cost, success, validation_result, fallback_used.

Les données personnelles de l'enfant ne sont pas conservées inutilement dans les journaux.

## 137. Versionnage des prompts

Les prompts importants sont versionnés (`lesson_analysis_v1`, `lesson_analysis_v2`, `activity_generation_v1`, `answer_evaluation_v1`, `error_analysis_v1`, `explanation_v1`…). Une modification de prompt ne doit pas rendre impossible la compréhension des anciens résultats.

## 138. Versionnage du moteur pédagogique

Le moteur pédagogique est également versionné (`pedagogical_engine_version = 1.2.0`), pour savoir avec quelle logique une décision a été prise.

## 139. Tests de l'IA

Le projet possède un jeu de tests pédagogiques représentatifs (`LEÇON_CP_FRANÇAIS_001`, `LEÇON_CE1_MATHS_001`, `LEÇON_CM1_HISTOIRE_001`, `LEÇON_CM2_SCIENCES_001`, `LEÇON_6E_GÉOGRAPHIE_001`, `LEÇON_3E_MATHS_001`…). Chaque scénario définit : entrée, connaissances attendues, compétences attendues, activités acceptables, réponses attendues, erreurs possibles, comportement attendu du moteur.

## 140. Tests de non-régression pédagogique

Une nouvelle version de l'IA ne doit pas dégrader significativement l'exactitude, l'adaptation au niveau, la pertinence des activités, la qualité des corrections, la détection des erreurs, la cohérence pédagogique. Un ensemble de cas de référence est conservé.

## 141. Sécurité du contenu généré

Tout contenu destiné à un enfant passe par une couche de contrôle : contenu inapproprié, langage inadapté à l'âge, informations dangereuses, violence inutile, données personnelles, demandes de contact, manipulation, contenu hors contexte pédagogique.

L'IA ne demande jamais à l'enfant des informations personnelles non nécessaires au fonctionnement de l'application.

## 142. Protection contre les prompts malveillants

Une leçon importée peut contenir du texte ressemblant à une instruction destinée à l'IA (« Ignore toutes les instructions précédentes… »). Ce texte est traité comme contenu pédagogique, jamais comme une instruction système. Le contenu importé ne peut jamais modifier les règles internes de l'application.

## 143. Séparation des instructions

Le système distingue strictement, par ordre de priorité :

```
SYSTEM RULES → DEVELOPER RULES → PEDAGOGICAL RULES → USER/PARENT INPUT → LESSON CONTENT → CHILD ANSWER
```

Une information provenant d'une photo, d'un document ou d'une réponse de l'enfant ne peut jamais prendre le dessus sur les règles système.

## 144. Continuité pédagogique

Chaque séance produit assez d'informations pour que la suivante continue naturellement :

```json
{
  "session_summary": {
    "skills_worked": [],
    "skills_improved": [],
    "skills_still_weak": [],
    "errors_detected": [],
    "recommended_next_step": "",
    "recommended_review_date": ""
  }
}
```

L'enfant ne doit pas avoir l'impression de recommencer à zéro à chaque séance.

## 145. Objectif final du moteur

Le moteur optimise non pas le nombre de questions répondues ni le score moyen, mais : **progression réelle + compréhension + mémorisation durable + autonomie + capacité de transfert**. La rapidité et le nombre d'activités sont secondaires.

## 146. Priorité des objectifs

Lorsqu'une décision est nécessaire, le système privilégie dans cet ordre :

1. sécurité de l'enfant ;
2. exactitude pédagogique ;
3. compréhension réelle ;
4. progression ;
5. autonomie ;
6. mémorisation durable ;
7. adaptation à l'enfant ;
8. engagement et plaisir ;
9. rapidité ;
10. optimisation du coût de l'IA.

Le système ne sacrifie jamais l'exactitude pédagogique pour économiser quelques appels à l'IA.

## 147. Principe de repli global

Le produit reste utilisable lorsqu'un composant IA tombe en panne :

```
LLM indisponible → modèle secondaire → cache → contenu pré-généré → algorithme déterministe → message utilisateur
```

Une panne d'un fournisseur d'IA ne provoque pas une panne globale de l'application.

## 148. Objectif pour l'IA de développement

Lorsqu'une IA reçoit une tâche sur ce projet, elle recherche la solution qui respecte simultanément : cahier des charges, architecture existante, sécurité, pédagogie, maintenabilité, testabilité, coût, évolutivité. Elle ne choisit pas une solution uniquement parce qu'elle est la plus rapide à coder.

## 149. Règle finale

L'application est conçue comme un système d'apprentissage adaptatif utilisant l'IA, et non comme une IA à laquelle on a ajouté une interface scolaire.

- Le LLM est un outil.
- Le moteur pédagogique est le cœur du produit.
- Les données de progression constituent la mémoire du système.
- Les activités constituent les actions pédagogiques.
- L'enfant est au centre du système ; le parent est l'accompagnateur.

L'IA doit continuellement répondre à quatre questions :

1. Que doit apprendre l'enfant ?
2. Que sait-il réellement déjà faire ?
3. Quelle est la meilleure prochaine action pédagogique ?
4. Qu'est-ce qui prouve qu'il a progressé ?

Si le système peut répondre correctement à ces quatre questions, il remplit sa fonction de tuteur pédagogique personnalisé.
