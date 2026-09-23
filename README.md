# Ludifun — coach de révision

L'enfant photographie sa leçon ; l'IA en extrait ce qu'il faut retenir, génère des
exercices adaptés (QCM, vrai/faux, texte à trous, cartes mémoire, associations,
questions ouvertes), corrige, puis adapte les révisions suivantes à ses erreurs
(niveaux de maîtrise 0-5 + répétition espacée).

📄 Spécification complète : [`docs/cahier-des-charges-v1.md`](docs/cahier-des-charges-v1.md)

```
backend/   API FastAPI + moteur pédagogique + intégration Claude
mobile/    Application Flutter (Android d'abord, iOS ensuite)
docs/      Cahier des charges V1
```

## Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# Mode hors-ligne (aucune clé nécessaire, analyse simplifiée par règles)
uvicorn app.main:app --reload --host 0.0.0.0

# Mode IA réel (Claude lit la photo et génère les exercices)
export ANTHROPIC_API_KEY=...
LUDIFUN_LLM_PROVIDER=anthropic uvicorn app.main:app --reload --host 0.0.0.0

pytest   # tests
```

API interactive : http://localhost:8000/docs

Variables d'environnement (préfixe `LUDIFUN_`, ou fichier `.env`) :

| Variable | Défaut | Rôle |
|---|---|---|
| `LUDIFUN_LLM_PROVIDER` | `fake` | `anthropic` pour utiliser Claude |
| `LUDIFUN_LLM_MODEL` | `claude-opus-5` | Modèle Claude |
| `LUDIFUN_DATABASE_URL` | `sqlite:///./ludifun.db` | ex. `postgresql+psycopg://user:pwd@host/ludifun` (installer `psycopg[binary]`) |
| `LUDIFUN_QUESTIONS_PER_NOTION` | `4` | Taille de la banque de questions |

## Application mobile

Le dossier `mobile/` contient le code Dart (`lib/`). Pour générer les projets
natifs Android/iOS puis lancer l'app :

```bash
cd mobile
flutter create --platforms=android,ios --org fr.ludifun .
flutter pub get
flutter run --dart-define=API_URL=http://10.0.2.2:8000   # émulateur Android
```

À ajouter après `flutter create` :
- **Android** (`android/app/src/main/AndroidManifest.xml`) : permission `CAMERA`, et
  `android:usesCleartextTraffic="true"` sur `<application>` pour le développement en HTTP local.
- **iOS** (`ios/Runner/Info.plist`) : `NSCameraUsageDescription` et
  `NSPhotoLibraryUsageDescription` (« Pour photographier ta leçon »).

## Données et vie privée

Les photos ne sont jamais enregistrées : elles sont lues en mémoire puis seul le
texte de la leçon est conservé. `DELETE /children/{id}` efface toutes les données
d'un enfant. Voir la section 8 du cahier des charges.
