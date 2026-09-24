# Ludifun — coach de révision

L'enfant photographie sa leçon ; l'IA en extrait ce qu'il faut retenir, construit une
séance de révision adaptée, analyse les erreurs et programme la prochaine révision.

📄 Cahier des charges complet (document de référence) : [`docs/cahier-des-charges-complet.md`](docs/cahier-des-charges-complet.md)
🛠️ Spécification technique (écarts, schéma, API, contrats IA, plan) : [`docs/specification-technique.md`](docs/specification-technique.md)
📄 Cahier des charges technique V1 (étapes 1 à 12) : [`docs/cahier-des-charges-v1.md`](docs/cahier-des-charges-v1.md)

```
backend/            API FastAPI + PostgreSQL          → voir backend/README.md
mobile/             Application Flutter (prototype, réécrite à l'étape 7)
docs/               Cahier des charges, spécification technique, guides
eval/               Évaluation sur de vraies leçons (protocole, exemples, grille)
docker-compose.yml  PostgreSQL + API pour le développement
```

## Avancement

Étapes 1 à 12 : cahier des charges V1 §18. Étapes 13 et suivantes : spécification technique §9.

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
| 9 | Socle Flutter : premier lancement, espaces parent et enfant | ✅ |
| 10 | Espace enfant : liaison (code, QR), accueil, photo, analyse, résumé | ✅ (essai sur téléphone à faire) |
| 11 | Espace enfant : jeux, correction, reprise des erreurs, bilan | ✅ (essai sur téléphone à faire) |
| 12 | Espace parent : compte, enfants, code et QR, tableau de bord, historique | ✅ (essai sur téléphone à faire) |
| 13 | Compétences et niveaux de compréhension | ✅ |
| 14 | Aide « Je n'ai pas compris », questions ouvertes, types d'erreurs | ✅ |
| 15 | Import de texte et lecture vérifiée | ⏭️ prochaine |
| 16 | Objectifs du parent : temps quotidien, plan avant un contrôle | |
| 17 | Adaptation en temps réel et engagement | |
| 18 | Tests avec de vraies familles (30 leçons, 5 enfants) | |
| 19 | Bêta Android (Play Store, test fermé) | |

Le prototype exploratoire qui a validé la faisabilité reste consultable dans l'historique
git (commit `3362b04`).

### Reste à faire avant la bêta publique (§16)

- hébergement : HTTPS et HSTS par un reverse proxy, API et base dans l'UE ;
- e-mails réels : un fournisseur d'envoi, puis la vérification de l'e-mail du parent ;
- conservation : suppression automatique d'un compte inactif depuis 12 mois, après un e-mail
  de prévenance (nécessite le fournisseur d'e-mails) ;
- limites de débit dans un stockage partagé (Redis) si l'API tourne sur plusieurs instances ;
- documents : politique de confidentialité, registre des traitements, analyse d'impact (AIPD),
  contrat de sous-traitance (DPA) avec le fournisseur d'IA.

## Démarrage rapide

```bash
docker compose up -d --build
curl http://localhost:8000/health/ready   # {"status":"ok","schema":"0004"}

docker compose exec api python -m app.tools.demo_family   # famille de démonstration (4 semaines)
cd mobile && flutter run                   # application (émulateur Android : API sur 10.0.2.2:8000)
```

Voir [`backend/README.md`](backend/README.md) et [`mobile/README.md`](mobile/README.md).

**Essayer sur un téléphone Android** (APK de test téléchargeable depuis GitHub, serveur sur votre
ordinateur) : [`docs/tester-sur-telephone.md`](docs/tester-sur-telephone.md).
