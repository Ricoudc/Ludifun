# Publication sur le Play Store en test fermé (étape 19)

Objectif : 20 familles testeuses qui installent Ludifun depuis le Play Store, sans APK à
transférer à la main.

## 1. Compte développeur et fiche de l'application

1. Créer un compte Google Play Console (frais uniques), si possible au nom de l'organisation.
   Google vérifie l'identité. **Un compte personnel récent doit faire un test fermé avec au moins
   12 testeurs pendant 14 jours avant de pouvoir publier en production.** Vérifier la règle en
   vigueur dans la Play Console : elle change.
2. Créer l'application : nom « Ludifun », langue par défaut français, application gratuite.
   Identifiant : `fr.ludifun.ludifun`. Il est définitif.
3. Activer la signature d'application par Google Play (par défaut). La clé ci-dessous est la
   **clé d'importation**.

## 2. Clé d'importation et secrets du dépôt

Sur un poste de confiance (pas sur le serveur) :

```bash
keytool -genkey -v -keystore ludifun-upload.jks -keyalg RSA -keysize 4096 -validity 10000 \
    -alias ludifun
base64 -w0 ludifun-upload.jks > ludifun-upload.jks.b64
```

Garder `ludifun-upload.jks` et son mot de passe dans un gestionnaire de mots de passe, avec deux
copies. Si la clé d'importation est perdue, Google peut la remplacer, mais seulement sur demande.

Dans GitHub, *Settings → Secrets and variables → Actions* :

| Nom | Type | Valeur |
|---|---|---|
| `ANDROID_KEYSTORE_BASE64` | secret | contenu de `ludifun-upload.jks.b64` |
| `ANDROID_KEYSTORE_PASSWORD` | secret | mot de passe du fichier |
| `ANDROID_KEY_ALIAS` | secret | `ludifun` |
| `ANDROID_KEY_PASSWORD` | secret | mot de passe de la clé |
| `LUDIFUN_API_URL` | variable | `https://api.ludifun.fr` (le serveur de [déploiement](deploiement.md)) |

## 3. Produire le bundle

GitHub, onglet *Actions* → **Android (Play Store)** → *Run workflow*. Le workflow se lance aussi
sur une étiquette `mobile-v1.0.0`. Il produit `app-release.aab` (artefact de l'exécution) :

- signé avec la clé d'importation ;
- adresse de l'API fixée à `LUDIFUN_API_URL`, en `https://` obligatoirement ; le réglage
  « adresse du serveur » des versions de test n'existe pas dans cette version ;
- numéro de version (`versionCode`) = numéro de l'exécution, toujours croissant ;
  `versionName` vient de `mobile/pubspec.yaml`.

Play Console → *Tests → Test fermé* → créer une piste « Familles bêta », ajouter l'`.aab`, une
note de version, puis la liste des testeurs (adresses Gmail des parents, ou un groupe Google).
Chaque parent reçoit un lien d'inscription au test, puis installe l'application depuis le Play
Store.

## 4. Formulaires de la Play Console

### Public cible et contenu

- Tranches d'âge : **moins de 13 ans compris** (6-8, 9-12), et 13-15. L'application relève donc
  du **programme Familles**. Ludifun en respecte les règles : aucune publicité, aucun SDK
  publicitaire ou de mesure d'audience, politique de confidentialité, données minimales, pas de
  collecte d'identifiants publicitaires.
- L'espace enfant ne demande ni e-mail ni nom de famille. Le compte est créé par le parent, qui
  donne son consentement pour chaque enfant.
- Publicités : **non**. Achats intégrés : **non** (bêta gratuite).

### Classification du contenu

Questionnaire IARC, catégorie « Référence, actualités ou éducation ». Ni violence, ni
contenu sexuel, ni langage grossier. Pas d'échange entre utilisateurs. Classification attendue :
PEGI 3.

### Sécurité des données (Data safety)

| Donnée (catégorie Play) | Collectée | Partagée | Pourquoi | Facultative |
|---|---|---|---|---|
| Adresse e-mail (parent) | oui | non | gestion du compte | non |
| Nom (prénom ou pseudo de l'enfant) | oui | non | fonctionnalités de l'application | non |
| Photos (pages de leçon) | oui, **traitées de façon éphémère** | non | fonctionnalités de l'application | oui (texte collé possible) |
| Autre contenu généré par l'utilisateur (texte des leçons, réponses, avis) | oui | non | fonctionnalités, analyse (améliorer l'application) | non |
| Activité dans l'application (séances, temps de révision) | oui | non | fonctionnalités, analyse | non |

- « Partagée » : non. Anthropic, l'hébergeur et le fournisseur d'e-mails sont des
  **fournisseurs de services** qui traitent les données pour notre compte : au sens du Play
  Store, ce n'est pas un partage.
- Données chiffrées en transit : **oui** (HTTPS obligatoire).
- Suppression possible : **oui**, dans l'application (enfant ou compte) et par la page web
  `https://<domaine>/suppression-compte`, à indiquer comme URL de suppression du compte.
- Politique de confidentialité : `https://<domaine>/confidentialite`.

### Autorisations

`INTERNET`, et `CAMERA`, ajoutée par la lecture du QR code de liaison (`mobile_scanner`). La
caméra n'est demandée qu'au moment de scanner. Les photos de leçons passent par l'application
Appareil photo du téléphone. La sauvegarde Android est désactivée : les jetons ne sont pas
restaurés sur un autre appareil.

## 5. Fiche du Play Store (brouillon)

**Description courte** (80 caractères au plus) :

> Photographie ta leçon, Ludifun en fait des jeux de révision adaptés à ton niveau.

**Description complète** :

> Ludifun aide les élèves du CP à la 3e à réviser leurs leçons, en jouant.
>
> 📸 Photographie ta leçon (ou colle son texte) : Ludifun en tire les notions importantes.
> 🎮 Révise avec des jeux courts : QCM, vrai ou faux, textes à trous, associations, défis
> rapides, cartes mémoire, questions à rédiger.
> ❓ Bloqué ? « Je n'ai pas compris » donne un indice, puis un rappel, puis un exemple, sans
> donner tout de suite la réponse.
> 📅 Ludifun te propose de revoir chaque notion au bon moment, et prépare un plan avant un contrôle.
>
> Pour les parents : un espace à part pour suivre les progrès, voir ce qui reste à revoir, fixer
> un temps de révision par jour et noter les contrôles à venir.
>
> Sans publicité. Les photos des leçons ne sont pas conservées. Le parent peut exporter ou
> supprimer toutes les données de son enfant à tout moment.
>
> Version bêta : vos retours comptent (« Donner mon avis » dans l'espace parent).

Visuels à préparer :
- icône 512 × 512 ;
- bannière 1024 × 500 ;
- au moins 4 captures de téléphone : accueil de l'enfant, activité, bilan, tableau de bord
  parent. Prendre ces captures avec la famille de démonstration (`app.tools.demo_family`),
  jamais avec les données d'un vrai enfant.

## 6. Avant d'inviter les familles

- [ ] Serveur en place et vérifié ([déploiement](deploiement.md) §3), sauvegarde restaurée une fois.
- [ ] Pages publiques complètes, sans « À COMPLÉTER ».
- [ ] Documents RGPD relus : [registre](rgpd/registre-des-traitements.md), [AIPD](rgpd/aipd.md),
      contrats de sous-traitance signés.
- [ ] Parcours complet sur un vrai téléphone, avec l'`.aab` installé depuis la piste de test :
      compte parent, e-mail de confirmation, enfant, liaison, photo, séance, bilan, avis,
      suppression du compte.
- [ ] Plafond du budget IA réglé (`LUDIFUN_AI_DAILY_BUDGET_USD` et console Anthropic).
