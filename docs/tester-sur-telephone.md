# Tester Ludifun sur un téléphone Android

Le code est sur GitHub ; il faut encore deux choses pour l'essayer :

- **le serveur** (API + base de données), qui tourne sur votre ordinateur avec Docker ;
- **l'application**, un APK de test fabriqué par GitHub à chaque envoi de code, à installer sur
  le téléphone.

Le téléphone joint l'ordinateur par le Wi-Fi : les deux doivent être sur **le même réseau**.

```
 Téléphone Android  ──Wi-Fi──►  Ordinateur : docker compose (API :8000 + PostgreSQL)
 (APK de test)                  IA factice par défaut, ou Claude avec une clé d'API
```

## 1. Lancer le serveur sur l'ordinateur

Prérequis : [Git](https://git-scm.com/) et [Docker Desktop](https://www.docker.com/products/docker-desktop/)
(démarré).

```bash
git clone https://github.com/Ricoudc/Ludifun.git
cd Ludifun
git checkout claude/revision-coach-app-8t5pfz   # tant que le travail n'est pas fusionné

docker compose up -d --build
docker compose exec api python -m app.tools.demo_family
```

La dernière commande crée une famille de démonstration et affiche :

```
  Espace parent : parent.demo@example.fr / demo-ludifun-2026
  Code pour lier un téléphone au profil d'Emma : 836128 (valable 10 minutes)
```

Vérification : <http://localhost:8000/health/ready> doit afficher `"status":"ok"`.

Par défaut, l'**IA est factice** : aucune clé n'est nécessaire, et toute photo est lue comme
l'une des trois leçons de référence (la Révolution française, les fractions ou les états de
l'eau). C'est idéal pour tester l'application, pas pour juger l'analyse des leçons (voir §5).

## 2. Trouver l'adresse de l'ordinateur sur le Wi-Fi

| Système | Commande ou réglage | Exemple |
|---|---|---|
| Windows | `ipconfig` → « Adresse IPv4 » de la carte Wi-Fi | `192.168.1.20` |
| macOS | `ipconfig getifaddr en0` | `192.168.1.20` |
| Linux | `hostname -I` (première adresse) | `192.168.1.20` |

Depuis le **navigateur du téléphone**, ouvrez `http://192.168.1.20:8000/health/ready` (avec
votre adresse). Si la page ne s'ouvre pas, voir « En cas de problème ».

## 3. Installer l'application

1. Sur GitHub (connecté à votre compte), ouvrez l'onglet **Actions** du dépôt, puis le
   workflow **Mobile**.
2. Ouvrez la dernière exécution **verte** de la branche `claude/revision-coach-app-8t5pfz`.
3. En bas de la page, section **Artifacts**, téléchargez **ludifun-apk-test** (un `.zip`,
   conservé 30 jours).
4. Décompressez-le : il contient `app-debug.apk`. Envoyez ce fichier sur le téléphone (câble
   USB, Google Drive, e-mail…).
5. Sur le téléphone, ouvrez le fichier et acceptez l'installation depuis cette source
   (« sources inconnues »). Si Play Protect prévient, choisissez « Installer quand même » :
   c'est normal pour une application de test non publiée.

> Avec Flutter installé et le téléphone branché en USB (débogage USB activé), on peut aussi
> lancer directement : `cd mobile && flutter run`.

## 4. Premier lancement

1. Sur l'écran « Qui utilise cet appareil ? », touchez **Serveur de test** en bas.
2. Saisissez l'adresse de l'ordinateur, par exemple `192.168.1.20:8000`, touchez **Tester**
   (« ✅ Serveur joignable »), puis **Enregistrer**. L'adresse est gardée sur le téléphone.
3. Choisissez votre espace :
   - **Je suis un parent** → `parent.demo@example.fr` / `demo-ludifun-2026` : enfants, tableau
     de bord d'Emma sur quatre semaines, historique, code et QR code de liaison ;
   - **Je suis un enfant** → le code affiché par l'outil de démonstration (ou par l'espace
     parent, *Lier un appareil*) : accueil d'Emma, mission du jour, photo d'une leçon, séance,
     bilan.

Un appareil sert **un seul espace**. Pour tester les deux :

- l'idéal : deux appareils (le téléphone du parent et celui ou la tablette de l'enfant) avec le
  même APK — la liaison par QR code se teste ainsi ;
- avec un seul téléphone : pour changer d'espace, *Paramètres Android → Applications → Ludifun →
  Stockage → Effacer les données*, puis ressaisir l'adresse du serveur.

## 5. Avec la vraie IA (analyse de vraies leçons)

Créez un fichier `.env` à la racine du dépôt (il n'est jamais envoyé sur GitHub) :

```
LUDIFUN_AI_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...
```

puis relancez `docker compose up -d`. Les photos sont alors lues et analysées pour de vrai
(quelques secondes à quelques dizaines de secondes par leçon, avec un coût par analyse).

## En cas de problème

| Symptôme | Piste |
|---|---|
| « Serveur injoignable » | Même Wi-Fi ? Pas de VPN sur le téléphone ? Le pare-feu de l'ordinateur doit autoriser le port 8000 sur le réseau privé (Windows : autoriser Docker Desktop). Un Wi-Fi public ou d'entreprise peut isoler les appareils : essayez le partage de connexion du téléphone. |
| `/health/ready` répond `database_unavailable` | `docker compose ps` : la base doit être `healthy` ; sinon `docker compose up -d` à nouveau. |
| Toute photo devient « La Révolution française » | C'est l'IA factice (voir §5). |
| « Ce code ne marche pas » | Le code dure 10 minutes et ne sert qu'une fois : demandez-en un nouveau dans l'espace parent. |
| L'outil de démonstration refuse | Le compte existe déjà : ajoutez `--replace`. |
| Pas d'« Artifacts » sur la page GitHub | L'exécution n'est pas terminée, a échoué, ou date de plus de 30 jours. |

Limites de cette version de test : APK de débogage (plus lent qu'une version publiée), serveur
en HTTP sur le réseau local uniquement. Sur iPhone, il faut un Mac avec Xcode (`flutter run`).
La publication sur le Play Store en test fermé est l'étape 14.
