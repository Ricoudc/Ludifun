# Audit UX/UI Ludifun — 12 novembre 2026

## Contexte vérifié
- Application observée : Flutter Android.
- Branche de référence au début du chantier : `main`, commit `17059ac8f5c774a5998ba3e7b1ec5a787518f9d5`.
- La PR #26 apporte une première harmonisation du thème, des cartes d'accueil et des raccourcis parent. Sa description annonce explicitement une refonte progressive, pas une refonte complète.
- L'APK publié dans la release `apk-test` est associé au commit `0d55dcab8cb077e6c3d59e1f86b544be1b8061e5`, antérieur au HEAD de main consulté. Le code de cet APK contient bien les premiers éléments de la PR #26, mais il ne faut pas le confondre avec une compilation garantie du HEAD courant.
- Aucun test sur appareil Android physique ni capture de l'application installée n'a été fourni ; le présent audit est un audit de code, pas un test visuel terrain.

## Constat UX/UI
### Points positifs
- Palette Material 3 cohérente, boutons principaux de 56 dp et contenu contraint à 480 dp.
- Actions essentielles accessibles depuis l'accueil enfant.
- États de progression, mission, erreurs, vide et hors-ligne présents.
- Le tableau de bord parent expose les indicateurs utiles et leurs définitions.

### Écarts restant à traiter
1. Accueil enfant : l'ancien écran empile trois grandes cartes d'action, deux grands panneaux bleus et plusieurs sections sans hiérarchie suffisamment nette.
2. Mascotte : le renard est un emoji dans un avatar, sans identité graphique propre ni rendu stable selon les polices/appareils.
3. Mission : le panneau reprend la couleur primaire de l'en-tête, ce qui réduit la distinction entre accueil et action.
4. Navigation : l'accès aux trois tâches est visible mais prend une place verticale importante ; les sections de contenu arrivent tard.
5. Parcours d'exercice : chaque type d'activité doit être audité séparément pour cohérence des consignes, réponses, progression, aide, correction et pause.
6. Espace parent : le tableau de bord est riche mais long ; il faut améliorer la synthèse initiale, les niveaux de lecture et l'accès aux détails sans masquer les données.
7. Accessibilité Android : vérifier TalkBack, tailles de texte système, contrastes, zones tactiles, orientation et petits écrans.
8. États système : vérifier visuellement chargement, erreur réseau, mode hors ligne, attente de validation adulte et reprise de séance.

## Tranche mise en œuvre dans cette branche
- Accueil enfant : mascotte vectorielle locale, accueil hiérarchisé, mission sur fond doux et trois raccourcis en grille.
- Accueil parent : bannière moins encombrante, identité visuelle plus sobre et introduction explicite à la liste des profils.
- Tableau de bord parent : titres de sections hiérarchisés et graphique encadré pour distinguer les blocs de lecture.
- Parcours de séance : progression annoncée avec une valeur accessible (« question x sur y »), carte de question plus respirante.
- Lecture audio des consignes : nom accessible explicite pour TalkBack.
- Toutes les familles de jeux qui réutilisent le composant commun `Prompt` bénéficient désormais d'un repère visuel compact pour la consigne.
- Correction : Ludi est également présent dans la bulle d'encouragement, avec son illustration vectorielle commune.
- Bilan : accueil de fin de séance avec Ludi, texte de félicitation et synthèse plus facile à parcourir.
- Routes, providers, API, règles pédagogiques et données métier conservés.
- Aucune modification de notation, maîtrise, synchronisation ou stockage.

## Suite de la feuille de route UX/UI
- P0 : tests visuels sur appareil Android réel (petit téléphone, téléphone standard, grande police).
- P0 : compléter l'audit visuel par famille de jeu (QCM, vrai/faux, réponse libre, association, ordre, dictée, calcul, géométrie, mémoire, cartes, etc.).
- P1 : harmoniser les écrans photo → analyse → relecture parent → séance → bilan.
- P1 : vérifier les contrastes, 200 % de taille de police, mode paysage, réseau instable et TalkBack sur appareil.
- P2 : bibliothèque complète d'expressions de Ludi et animations facultatives, après validation de la direction artistique.
- P2 : captures de référence automatisées pour les tailles Android courantes.

## Critères de validation
- Tests Flutter et analyse statique réussis.
- Aucune route ni action existante perdue.
- Aucun overflow sur largeur 320 dp et avec texte agrandi.
- Les trois actions principales sont visibles sans défilement horizontal.
- Les libellés restent compréhensibles sans couleur ni emoji.
- Le parcours enfant reste utilisable au TalkBack.


## État de validation au 12 novembre 2026
- Modifications de cette tranche poussées dans la PR #47, sans fusion dans main.
- Les workflows GitHub Actions ont été déclenchés sur le commit de la tranche ; leur résultat doit être vérifié avant de déclarer la PR prête.
- Aucun appareil Android physique n'est accessible depuis ce travail : TalkBack, débordements visuels réels et rendu sur les tailles de police du téléphone restent à confirmer sur l'appareil de test.
