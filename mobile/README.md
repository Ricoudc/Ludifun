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

Au premier lancement, l'appareil choisit son espace :

- **parent** : connexion ou création du compte (e-mail et mot de passe) ;
- **enfant** : code à 6 chiffres ou QR code affiché dans l'espace parent, puis « C'est toi, Emma ? ».

Espace enfant : mission du jour et dernières leçons, photo (1 à 6 pages, compressées sur le
téléphone : 2000 px, JPEG 80, sans métadonnées EXIF), suivi de l'analyse, résumé de la leçon.
Les photos restent sur le téléphone jusqu'à la fin de l'analyse, puis sont effacées.

Les identifiants restent sur l'appareil, chiffrés par le système. Le jeton d'accès du
parent (15 minutes) est renouvelé automatiquement ; si l'appareil de l'enfant est délié,
l'application revient au premier lancement.

| Dossier | Contenu |
|---|---|
| `lib/app/` | application, thème, routeur (redirection selon l'espace) |
| `lib/core/` | configuration, client API et intercepteur de jetons, session, stockage sécurisé |
| `lib/models/` | formats de l'API |
| `lib/features/` | écrans : premier lancement, espace parent, liaison, accueil, photo, analyse, leçon |
| `test/` | faux serveur, tests du client et des jetons, tests de widgets des deux espaces |
