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
| 5 | Mesure sur de vraies leçons | 🟡 outillage prêt et à jour des étapes 13 à 15 (compétences, aides, passages douteux, noms personnels), en attente des leçons et d'une clé API ([`eval/`](eval/README.md)) |
| 6 | API : comptes parent, profils enfants, liaison par code / QR | ✅ |
| 7 | API : leçons et séances, mission du jour | ✅ |
| 8 | API : tableau de bord parent | ✅ |
| 9 | Socle Flutter : premier lancement, espaces parent et enfant | ✅ |
| 10 | Espace enfant : liaison (code, QR), accueil, photo, analyse, résumé | ✅ (essai sur téléphone à faire) |
| 11 | Espace enfant : jeux, correction, reprise des erreurs, bilan | ✅ (essai sur téléphone à faire) |
| 12 | Espace parent : compte, enfants, code et QR, tableau de bord, historique | ✅ (essai sur téléphone à faire) |
| 13 | Compétences et niveaux de compréhension | ✅ |
| 14 | Aide « Je n'ai pas compris », questions ouvertes, types d'erreurs | ✅ |
| 15 | Import de texte et lecture vérifiée | ✅ |
| 16 | Objectifs du parent : temps quotidien, plan avant un contrôle | ✅ |
| 17 | Adaptation en temps réel et engagement | ✅ |
| 18 | Tests avec de vraies familles (30 leçons, 5 enfants) | 🟡 outillage prêt (avis dans l'application, rapport, [protocole](docs/tests-familles.md)), en attente des familles |
| 19 | Bêta Android (Play Store, test fermé) | 🟡 prête à déployer ([serveur](docs/deploiement.md), [Play Store](docs/play-store.md), [RGPD](docs/rgpd/registre-des-traitements.md)), en attente des comptes, fournisseurs et familles |
| 20 | Missions et gamification : XP selon l'effort, niveau, série, badges (V2) | ✅ |
| 21 | Activités graphiques : remettre dans l'ordre, frise, ranger dans les cases, memory (V2) | ✅ (coloriage et carte reportés) |

Le prototype exploratoire qui a validé la faisabilité reste consultable dans l'historique
git (commit `3362b04`).

### Reste à faire avant la bêta (§16)

Le code est prêt (étape 19) : HTTPS et HSTS par Caddy, e-mails SMTP, confirmation de l'e-mail
du parent, suppression des comptes inactifs, sauvegardes chiffrées, pages de confidentialité et
de suppression du compte, bundle signé pour le Play Store. Restent des décisions et des comptes
à créer :

- choisir l'éditeur, l'hébergeur et le fournisseur d'e-mails dans l'UE ; signer les contrats de
  sous-traitance (DPA), y compris avec Anthropic ;
- faire relire la politique de confidentialité, le [registre](docs/rgpd/registre-des-traitements.md)
  et l'[AIPD](docs/rgpd/aipd.md) ;
- déployer ([`docs/deploiement.md`](docs/deploiement.md)) et publier en test fermé
  ([`docs/play-store.md`](docs/play-store.md)) ;
- plus tard : limites de débit dans un stockage partagé (Redis) si l'API tourne sur plusieurs
  instances.

## Démarrage rapide

**Windows, sans ligne de commande** : double-cliquer sur `Demarrer-Ludifun.bat` (choix de l'IA,
serveur, adresse à saisir sur le téléphone) ; voir
[`docs/tester-sur-telephone.md`](docs/tester-sur-telephone.md).

```bash
docker compose up -d --build
curl http://localhost:8000/health/ready   # {"status":"ok","schema":"0013"}

docker compose exec api python -m app.tools.demo_family   # famille de démonstration (4 semaines)
cd mobile && flutter run                   # application (émulateur Android : API sur 10.0.2.2:8000)
```

Voir [`backend/README.md`](backend/README.md) et [`mobile/README.md`](mobile/README.md).

**Essayer sur un téléphone Android** (APK de test téléchargeable depuis GitHub, serveur sur votre
ordinateur) : [`docs/tester-sur-telephone.md`](docs/tester-sur-telephone.md).
