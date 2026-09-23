# Ludifun — coach de révision

L'enfant photographie sa leçon ; l'IA en extrait ce qu'il faut retenir, construit une
séance de révision adaptée, analyse les erreurs et programme la prochaine révision.

📄 Cahier des charges technique V1 : [`docs/cahier-des-charges-v1.md`](docs/cahier-des-charges-v1.md)

```
backend/            API FastAPI + PostgreSQL          → voir backend/README.md
mobile/             Application Flutter (prototype, réécrite à l'étape 7)
docs/               Vision produit et cahier des charges V1
eval/               Évaluation sur de vraies leçons (protocole, exemples, grille)
docker-compose.yml  PostgreSQL + API pour le développement
```

## Avancement

Vision à long terme : [`docs/vision.md`](docs/vision.md) (espaces parent et enfant, bibliothèque d'activités, versions V0 à V6).
Plan de la V1 : cahier des charges §18.

| # | Étape | État |
|---|---|---|
| 1 | Socle : structure backend, PostgreSQL, migrations, intégration continue | ✅ |
| 2 | Domaine : connaissances et activités | ✅ |
| 3 | Domaine : séance, notation, mémorisation | ✅ |
| 4 | Pipeline IA (+ outil `python -m app.tools.analyze`) | ✅ |
| 5 | Mesure sur de vraies leçons | 🟡 outillage prêt, en attente des leçons ([`eval/`](eval/README.md)) |
| 6 | API : comptes parent, profils enfants, liaison par code / QR | ✅ |
| 7 | API : leçons et séances, mission du jour | ✅ |
| 8 | API : tableau de bord parent | ✅ |
| 9 | Socle Flutter | ⏭️ prochaine |
| 10-12 | Application Flutter : espace enfant, espace parent | |
| 13-14 | Tests avec de vraies familles, bêta Android | |

Le prototype exploratoire qui a validé la faisabilité reste consultable dans l'historique
git (commit `3362b04`).

## Démarrage rapide

```bash
docker compose up -d --build
curl http://localhost:8000/health/ready   # {"status":"ok","schema":"0001"}
```
