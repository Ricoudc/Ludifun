# Feuille de route — novembre 2026

Établie à partir d'une revue extérieure du dépôt (novembre 2026), confrontée au code. Principe
retenu : **la fiabilité pédagogique d'abord**, pas l'accumulation de jeux, de badges ou de
fonctions d'IA. La promesse à tenir : un enfant photographie n'importe quelle leçon de son
programme, et Ludifun la lui fait apprendre, comprend ses difficultés et l'accompagne jusqu'à la
maîtrise.

Légende : ✅ fait · 🟡 en partie · ⬜ à faire. Les références « § » renvoient à
`specification-technique.md`.

## Ordre de travail

| Ordre | Chantier | Priorité | État |
|---|---|---|---|
| 0 | Petites corrections : artefact de test versionné, adresses d'IA internes | Haute | ✅ |
| 1 | Fiabilité pédagogique sur de vraies leçons | Très haute | 🟡 |
| 2 | Performances de l'IA (Ollama sur une carte de 8 Go) | Très haute | 🟡 |
| 3 | Moteur adaptatif : comprendre pourquoi l'enfant se trompe | Très haute | ✅ |
| 4 | Tableau de bord parental : « Que travailler cette semaine ? » | Haute | ✅ |
| 5 | Expérience de l'enfant : professeur virtuel, oral | Haute | 🟡 |
| 6 | Distribution : téléphones réels, familles, RGPD, Google Play | Haute | 🟡 |

## 0. Petites corrections

- ✅ `backend/.coverage` (mesure de couverture) retiré du dépôt et ignoré.
- ✅ Adresses d'IA libres des familles (Ollama, « autre service ») : jamais les services internes
  du serveur (base, moteur de recherche), les adresses de métadonnées du nuage (169.254.x.x) ni
  une adresse avec identifiants ; en production, ni le réseau local ni la machine elle-même, sauf
  l'Ollama réglé par le serveur (§5.70). Limite connue : un nom de domaine qui pointerait vers une
  adresse interne n'est pas résolu à l'enregistrement.

## 1. Fiabilité pédagogique (avant toute diffusion à d'autres familles)

Fait :
- ✅ Contrôles du code sur toute sortie de l'IA (schémas, citations exactes, `validation.py`).
- ✅ Confiance par notion et passages douteux montrés au parent (§5.38).
- ✅ Le parent relit, corrige et valide chaque leçon avant l'enfant (§5.69).
- ✅ Le parent essaie la leçon comme son enfant, sans rien compter pour lui, et note les erreurs
  à corriger (§5.84).
- ✅ Les erreurs notées pendant l'essai sont gardées sur la notion jusqu'à « C'est corrigé » ;
  essai de toute la leçon (§5.90) ; « Revérifier la leçon » avec les contrôles d'aujourd'hui (§5.91).
- ✅ Une question garde son contexte (§5.87) ; un texte en anglais hors leçon d'anglais est écarté.
- ✅ Outil d'évaluation sur les vraies leçons de la famille (`Ludifun.bat`, choix 12, §5.55).

À faire :
- ⬜ Corpus de 30 vraies leçons (manuscrites, schémas, tableaux, cartes, maths) et mesure avec le
  choix 12. Objectifs proposés (à confirmer, pas encore mesurés) :

  | Indicateur | Objectif |
  |---|---|
  | Notions essentielles reconnues | ≥ 95 % |
  | Exercices à réponse incontestable | ≥ 98 % |
  | Questions adaptées à la classe | ≥ 95 % |
  | Exercices sans ambiguïté | ≥ 98 % |
  | Erreurs pédagogiques graves | 0 |

- ⬜ Notation automatique des séances, avec relecture humaine d'un échantillon.
- ✅ Tests de non-régression pédagogique : une séance qui marchait ne doit pas se dégrader quand
  le moteur change (séances de référence rejouées, comparées), §5.79.

## 2. Performances de l'IA

Fait :
- ✅ Photos réduites (1 024 points, 768 en cas d'échec), une demande à la fois sur la carte
  graphique, réponses limitées, matériel par lots, mesure du débit.
- ✅ Lecture des photos par Tesseract, mode `auto` (le modèle de vision seulement pour les pages
  mal lues), §5.65 ; limite par minute des IA en ligne attendue (§5.67).
- ✅ Temps de chaque étape mesuré (« Voir ce qui se passe », page `/suivi`).

À faire :
- ⬜ Mesures sur le PC de la famille (RX 6600) : plusieurs modèles, avec et sans Tesseract.
- ⬜ Vérifier la lecture de l'écriture manuscrite en mode `auto`.
- ⬜ Choix du modèle par étape (petit modèle rapide pour la correction, plus grand pour l'analyse)
  conseillé automatiquement selon la carte graphique.
- ⬜ Garder le découpage actuel : sur 8 Go, tout traiter en même temps ralentirait.

## 3. Moteur adaptatif

Fait :
- ✅ Niveaux de compréhension (reconnaître → transférer), maîtrise et difficulté par notion,
  oubli estimé, répétition espacée (§5.32, §5.37).
- ✅ Catégories d'erreurs (§5.34), remédiation après deux échecs, reprise des erreurs.

À faire :
- ✅ Profil par notion visible : réussite, temps de réponse, tentatives, type d'erreur, sans aide,
  transfert, dernière révision ; et la décision qui en découle (« révision espacée », « exercices
  en plus », « reprendre les bases »), §5.73.
- ✅ Revenir sur une connaissance préalable quand une notion échoue (§5.72).
- ✅ Exercice neuf généré sur une erreur qui revient (§118, §5.74).

## 4. Tableau de bord parental

Fait : « En bref » sur 7 jours, compétences, erreurs, aides demandées, programme, rappels,
assistant parent.

À faire :
- ✅ **« Que travailler avec mon enfant cette semaine ? »** : trois actions concrètes, tirées des
  données, sans demander au parent d'être enseignant (§5.71).
- ✅ Y ajouter la matière qui décroche (moyenne en baisse sur plusieurs semaines), §5.75.
- ✅ Temps passé à apprendre, par semaine (écrit sous le graphique « Progrès », §5.75).

## 4 bis. Espace parent (novembre 2026)

- ✅ État de l'installation dit au parent : IA, clé, carte graphique et modèles qui tiendraient,
  dernières leçons (§5.89).
- ✅ Un second parent dans la famille (§5.92).
- ✅ Bilan de la semaine par e-mail, au choix du parent (§5.93) ; reste à brancher un fournisseur
  d'e-mails et une tâche planifiée sur le PC de la famille.
- ⬜ Notifications sur le téléphone (« ta leçon est prête », « c'est l'heure de réviser ») :
  demandent un service de notifications (Firebase) ou une extension native, à essayer sur un
  vrai téléphone.

## 5. Expérience de l'enfant

Fait : « Enseigne-moi », aides progressives, voix (dictées, sons, anglais), jeux visuels, jeu du
jour, missions du jour.

À faire :
- ✅ Un personnage qui accompagne la séance et explique l'erreur à l'âge de l'enfant
  (« Tu y es presque ! Regarde la deuxième étape. ») : Ludi, §5.76.
- ✅ Réponses à voix haute (reconnaissance vocale sur le téléphone), pour les plus jeunes (§5.78) ;
  reste à essayer sur de vrais téléphones.
- ✅ Garde-fou : le jeu ne doit pas prendre le pas sur l'apprentissage (§5.77).
- ✅ Affichage : taille du texte, lecture facile, contraste renforcé (§5.94) ; reste une police
  pensée pour la dyslexie et la vérification de tous les jeux en très grand sur un téléphone.
- ⬜ Séance comme machine à états explicite (§124) : à décider avec les séances de référence.

## 6. Distribution

À faire :
- ⬜ Essais sur de vrais téléphones Android, puis avec cinq familles (`tests-familles.md`).
- 🟡 Vérifier sauvegarde et restauration en conditions réelles : procédure rejouée sur une vraie
  base, ancienne version comprise (§5.83) ; reste l'essai par `Ludifun.bat` sur le PC, et sur un
  autre PC depuis une clé USB.
- 🟡 Finaliser les documents RGPD et valider l'analyse d'impact : brouillons remis à jour d'après le
  code (IA au choix, images, voix, §5.82) ; restent les DPA, la liste des fournisseurs proposés et la
  validation par un juriste ou un DPO.
- 🟡 Contrats avec les fournisseurs d'IA, supervision et gestion des incidents : erreurs du
  serveur comptées dans le suivi (§5.95) ; restent les contrats et un outil de supervision.
- ⬜ Version iPhone : le projet `ios` existe, rien n'est construit ni testé (il faut un Mac).
- ⬜ Bêta fermée sur Google Play (`play-store.md`).

## Suivi technique

- ✅ Prompts versionnés, version enregistrée avec chaque analyse ; règles du moteur versionnées.
- ✅ Comparer deux versions de prompt ou de modèle sur le même corpus, et revenir à la meilleure
  (§5.81) ; à faire tourner sur les vraies leçons.
- ✅ Coût par leçon et qualité des exercices dans la page de suivi (§5.80).
