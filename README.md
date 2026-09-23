# Ludifun — coach de révision

L'enfant photographie sa leçon ; l'IA en extrait ce qu'il faut retenir, construit une
séance de révision adaptée, analyse les erreurs et programme la prochaine révision.

📄 Cahier des charges technique V1 : [`docs/cahier-des-charges-v1.md`](docs/cahier-des-charges-v1.md)

```
backend/            API FastAPI + PostgreSQL          → voir backend/README.md
mobile/             Application Flutter (prototype, réécrite à l'étape 7)
docs/               Cahier des charges V1
docker-compose.yml  PostgreSQL + API pour le développement
```

## Avancement (plan §18 du cahier des charges)

| # | Étape | État |
|---|---|---|
| 1 | Socle : structure backend, PostgreSQL, migrations, intégration continue | ✅ |
| 2 | Domaine : connaissances et activités | ✅ |
| 3 | Domaine : séance, notation, mémorisation | ⏭️ prochaine |
| 4 | Pipeline IA | |
| 5 | Premier test de qualité sur de vraies leçons | |
| 6 | API v1 | |
| 7-9 | Application Flutter | |
| 10-13 | Tests réels, gamification, bêta Android, iOS | |

Le prototype exploratoire qui a validé la faisabilité reste consultable dans l'historique
git (commit `3362b04`).

## Démarrage rapide

```bash
docker compose up -d --build
curl http://localhost:8000/health/ready   # {"status":"ok","schema":"0001"}
```
