# Déploiement de la bêta (étape 19)

Un seul serveur dans l'Union européenne suffit pour la bêta (quelques dizaines de familles) :
PostgreSQL, l'API, Caddy (HTTPS) et deux tâches quotidiennes, dans
[`deploy/docker-compose.prod.yml`](../deploy/docker-compose.prod.yml).

```
Internet ──443──▶ Caddy (HTTPS, HSTS) ──▶ API ──▶ PostgreSQL
                                           ├── retention (chaque jour : comptes inactifs)
                                           └── backup    (chaque nuit : sauvegarde chiffrée)
```

## 1. Choisir les fournisseurs (dans l'UE)

| Besoin | Exemples hébergés dans l'UE | À vérifier |
|---|---|---|
| Serveur virtuel (2 vCPU, 4 Go, 40 Go) | Scaleway (Paris), OVHcloud (Roubaix, Gravelines), Hetzner (Falkenstein, Helsinki) | centre de données dans l'UE, contrat de sous-traitance (DPA) signé |
| E-mails (SMTP) | Brevo, Scaleway Transactional Email, Mailjet | serveurs dans l'UE, DPA, domaine d'envoi vérifié |
| IA | Anthropic (par défaut), ou Mistral AI (hébergé en France), OpenAI, Google, Groq, xAI via `LUDIFUN_AI_PROVIDER` | DPA signé, pas d'entraînement sur les données envoyées (offres payantes : l'offre gratuite de Gemini peut les réutiliser), clé dédiée à la production, plafond de dépense dans la console |

Chaque fournisseur est à reporter dans le [registre des traitements](rgpd/registre-des-traitements.md)
et dans les réglages des pages publiques (ci-dessous). La politique de confidentialité
(`backend/app/web/confidentialite.html`), le registre et l'[AIPD](rgpd/aipd.md) décrivent
Anthropic : avec une autre IA, mettez-les à jour (nom, pays, transfert hors UE, entraînement).

## 2. Préparer le serveur

1. Créer le serveur (Debian ou Ubuntu récents), avec une clé SSH et le pare-feu ouvert
   uniquement sur 22, 80 et 443.
2. Installer Docker et le plugin Compose, puis activer les mises à jour de sécurité
   automatiques (`unattended-upgrades`).
3. Faire pointer le nom de domaine de l'API (par exemple `api.ludifun.fr`, enregistrements A et
   AAAA) vers le serveur.
4. Chez le fournisseur d'e-mails : vérifier le domaine d'envoi et publier SPF, DKIM et DMARC.
   Sans eux, les liens de confirmation arrivent dans les indésirables.

## 3. Configurer et lancer

```bash
git clone https://github.com/Ricoudc/Ludifun.git && cd Ludifun
cp deploy/.env.example deploy/.env && chmod 600 deploy/.env
# Remplir deploy/.env : domaine, secrets (openssl rand -base64 48), clé Anthropic, SMTP,
# éditeur et contact des pages publiques, clé publique age des sauvegardes.

docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d --build
curl https://api.ludifun.fr/health/ready     # {"status":"ok","schema":"0014"}
```

Compose refuse de démarrer si une variable obligatoire est vide. Au démarrage, l'API applique
les migrations. Elle écrit un avertissement dans son journal si les pages publiques ne sont pas
entièrement renseignées (`LUDIFUN_LEGAL_ENTITY`, `LUDIFUN_CONTACT_EMAIL`,
`LUDIFUN_HOSTING_PROVIDER`, `LUDIFUN_EMAIL_PROVIDER`).

Vérifications après le premier lancement :

- `https://<domaine>/confidentialite` et `https://<domaine>/suppression-compte` s'affichent,
  sans « À COMPLÉTER » ;
- `https://<domaine>/docs` répond 404 (documentation fermée en production) ;
- créer un compte parent de test : l'e-mail « Confirmez votre adresse » arrive, le lien ouvre
  la page de confirmation ; puis supprimer ce compte depuis l'application ;
- `curl -I https://<domaine>/health` montre `strict-transport-security`.

## 4. Sauvegardes

Le service `backup` écrit chaque nuit dans `deploy/backups/` un `pg_dump` chiffré pour une clé
publique [age](https://age-encryption.org). Il efface les sauvegardes de plus de 30 jours. La
clé privée ne va jamais sur le serveur :

```bash
age-keygen -o cle-ludifun.txt        # sur votre poste ; garder ce fichier en lieu sûr (2 copies)
# la ligne « public key: age1… » va dans BACKUP_AGE_RECIPIENT
```

- Copier `deploy/backups/` hors du serveur, par exemple chaque nuit avec `rsync` ou `rclone`
  vers un stockage objet dans l'UE.
- **Tester une restauration** avant d'accueillir les familles, puis une fois par mois :

```bash
age -d -i cle-ludifun.txt ludifun-AAAAMMJJ-HHMM.dump.age > ludifun.dump
createdb ludifun_restauration && pg_restore -d ludifun_restauration ludifun.dump
```

## 5. Supervision

| Quoi | Comment |
|---|---|
| Disponibilité | sonde externe toutes les 5 minutes sur `https://<domaine>/health/ready` (503 si la base est injoignable), alerte par e-mail |
| Budget IA | le journal de l'API écrit une alerte quand le plafond du jour est atteint (`ai_budget`) ; plafond aussi réglé dans la console Anthropic |
| Erreurs | `docker compose -f deploy/docker-compose.prod.yml logs --since 24h api \| grep -E "ERROR\|WARNING"` |
| E-mails | les échecs d'envoi sont journalisés (`ludifun.email`), sans destinataire ni contenu |
| Conservation | `docker compose … logs retention` : prévenus, supprimés, échecs |
| Usage des familles | `docker compose … exec api python -m app.tools.pilot_report` ([tests en famille](tests-familles.md)) |

Les journaux ne contiennent ni texte de leçon, ni jeton, ni lien d'e-mail : Caddy retire le
paramètre `jeton` et l'en-tête `Authorization` de son journal d'accès. Leur taille est bornée
(3 × 10 Mo par service).

## 6. Mettre à jour

```bash
git pull
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d --build
```

Les migrations passent au démarrage de l'API. Les sauvegardes de la nuit précédente
permettent de revenir en arrière. Une migration qui supprime des données doit d'abord être
essayée sur une restauration.

## 7. Limites connues de la bêta

- Une seule instance d'API : les limites de débit sont gardées en mémoire. Il faudra un
  stockage partagé (Redis) pour passer à plusieurs instances.
- Pas de réplique de la base : en cas de panne du serveur, on restaure la dernière sauvegarde
  (perte possible d'une journée).
