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
| 3 | Moteur adaptatif : comprendre pourquoi l'enfant se trompe | Très haute | 🟡 |
| 4 | Tableau de bord parental : « Que travailler cette semaine ? » | Haute | ✅ en partie |
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
- ⬜ Tests de non-régression pédagogique : une séance qui marchait ne doit pas se dégrader quand
  le moteur change (séances de référence rejouées, comparées).

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
- ⬜ Profil par notion visible : réussite, temps de réponse, tentatives, type d'erreur, sans aide,
  transfert, dernière révision ; et la décision qui en découle (« révision espacée », « exercices
  en plus », « reprendre les bases »).
- ✅ Revenir sur une connaissance préalable quand une notion échoue (§5.72).
- ⬜ Exercice neuf généré sur une erreur qui revient (§118).

## 4. Tableau de bord parental

Fait : « En bref » sur 7 jours, compétences, erreurs, aides demandées, programme, rappels,
assistant parent.

À faire :
- ✅ **« Que travailler avec mon enfant cette semaine ? »** : trois actions concrètes, tirées des
  données, sans demander au parent d'être enseignant (§5.71).
- ⬜ Y ajouter la matière qui décroche (moyenne en baisse sur plusieurs semaines).
- ⬜ Temps passé à apprendre, par semaine.

## 5. Expérience de l'enfant

Fait : « Enseigne-moi », aides progressives, voix (dictées, sons, anglais), jeux visuels, jeu du
jour, missions du jour.

À faire :
- ⬜ Un personnage qui accompagne la séance et explique l'erreur à l'âge de l'enfant
  (« Tu y es presque ! Regarde la deuxième étape. »).
- ⬜ Réponses à voix haute (reconnaissance vocale), pour les plus jeunes.
- ⬜ Garde-fou : le jeu ne doit pas prendre le pas sur l'apprentissage.

## 6. Distribution

À faire :
- ⬜ Essais sur de vrais téléphones Android, puis avec cinq familles (`tests-familles.md`).
- ⬜ Vérifier sauvegarde et restauration en conditions réelles.
- ⬜ Finaliser les documents RGPD et valider l'analyse d'impact (aujourd'hui des brouillons).
- ⬜ Contrats avec les fournisseurs d'IA, supervision et gestion des incidents.
- ⬜ Bêta fermée sur Google Play (`play-store.md`).

## Suivi technique

- ✅ Prompts versionnés, version enregistrée avec chaque analyse ; règles du moteur versionnées.
- ⬜ Comparer deux versions de prompt ou de modèle sur le même corpus, et revenir à la meilleure.
- ⬜ Coût par leçon et qualité des exercices dans la page de suivi.
