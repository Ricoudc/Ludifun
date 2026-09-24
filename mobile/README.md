# Ludifun — application Flutter

Espace enfant et espace parent (cahier des charges §3 et §14). Riverpod, go_router, dio,
jetons dans `flutter_secure_storage`.

```bash
flutter pub get
flutter analyze && flutter test

# API locale (docker compose up à la racine) ; l'émulateur Android joint l'hôte par 10.0.2.2.
flutter run                                              # émulateur Android ou simulateur iOS
flutter run --dart-define=API_URL=http://192.168.1.20:8000   # téléphone réel sur le même réseau
```

Sans émulateur, l'application s'essaie dans un navigateur, servie à la même adresse que l'API
(pas de CORS côté API) :

```bash
flutter build web --no-web-resources-cdn
npx http-server build/web -p 8080 --proxy http://localhost:8000   # puis http://localhost:8080
```

Pour une application déjà remplie, créez d'abord la famille de démonstration
(`python -m app.tools.demo_family`, voir `backend/README.md`) : espace parent
`parent.demo@example.fr` / `demo-ludifun-2026`, et un code pour lier le téléphone au profil d'Emma.

Sur un vrai téléphone : l'APK de test est produit par l'intégration continue (onglet *Actions*,
« ludifun-apk-test ») et l'adresse du serveur se règle sur l'écran de premier lancement (versions
de test uniquement). Pas à pas : [`docs/tester-sur-telephone.md`](../docs/tester-sur-telephone.md).

Play Store (test fermé) : le workflow « Android (Play Store) » produit un bundle signé, avec
l'adresse de l'API fixée (`--dart-define=API_URL=https://…`). La signature vient de
`android/key.properties`, jamais versionné. Pas à pas : [`docs/play-store.md`](../docs/play-store.md).

Au premier lancement, l'appareil choisit son espace :

- **parent** : connexion ou création du compte (e-mail et mot de passe) ;
- **enfant** : code à 6 chiffres ou QR code affiché dans l'espace parent, puis « C'est toi, Emma ? ».

Espace enfant : mission du jour et dernières leçons, photo (1 à 6 pages, compressées sur le
téléphone : 2000 px, JPEG 80, sans métadonnées EXIF), suivi de l'analyse, résumé de la leçon.
Les photos restent sur le téléphone jusqu'à la fin de l'analyse, puis sont effacées. Une leçon
peut aussi être collée en texte ; si un mot de la photo est mal lu, l'écran « Peux-tu vérifier ? »
le fait confirmer ou corriger avant l'analyse.

Espace parent (écrans P1 à P4) : inscription (prénom facultatif), connexion, mot de passe oublié (le lien de l'e-mail
`ludifun://app/parent/nouveau-mot-de-passe?jeton=…` ouvre l'application), profils des enfants avec
consentement parental, code à 6 chiffres et QR code de liaison, tableau de bord de la semaine,
objectifs (temps par jour, matière à privilégier, contrôles à venir et leur plan de révision),
compétences par leçon (niveau 0 à 5 de chaque compétence et notion, et ce qui manque encore),
historique des séances, appareils liés, export des données d'un enfant (fichier JSON, par la
feuille de partage du téléphone), suppression d'un enfant ou du compte, « Donner mon avis » (note
et message, menu *Mon compte*), bandeau « Confirmez votre adresse » avec renvoi du lien, lien
`ludifun://app/parent/verifier-email?jeton=…`, politique de confidentialité ouverte dans le
navigateur (inscription et menu *Mon compte*). Le parent peut aussi photographier une leçon pour son enfant.

Séance (écrans 5 à 7, une seule route) : les 6 activités (QCM, vrai ou faux, texte à trou,
association, défi rapide chronométré, carte mémoire) viennent d'un registre de widgets ; un type
inconnu est sauté sans être noté. Correction immédiate, reprise des erreurs, bilan (avec l'XP gagnée,
le progrès du jour, les nouveaux badges et « Tu as aimé cette séance ? » 😕 🙂 😍, facultatif) et
« Revoir mes erreurs ». Chaque bloc de la séance est une étape de la mission (« 🚀 Étape 2 / 4 »).
L'accueil montre l'XP, le niveau, la série et « Mes badges » ; le tableau de bord du parent aussi. Une séance interrompue reprend à la première activité sans réponse.

Les identifiants restent sur l'appareil, chiffrés par le système. Le jeton d'accès du
parent (15 minutes) est renouvelé automatiquement ; si l'appareil de l'enfant est délié,
l'application revient au premier lancement.

| Dossier | Contenu |
|---|---|
| `lib/app/` | application, thème, routeur (redirection selon l'espace) |
| `lib/core/` | configuration, client API et intercepteur de jetons, session, stockage sécurisé |
| `lib/models/` | formats de l'API |
| `lib/features/` | écrans : premier lancement, espace parent, liaison, accueil, photo, analyse, leçon, séance, bilan |
| `test/` | faux serveur, tests du client et des jetons, tests de widgets des deux espaces |
