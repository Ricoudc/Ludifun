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

## Le plus simple : Windows, en double-cliquant

Une fois le dépôt téléchargé (`git clone`, ou le ZIP de GitHub décompressé) et Docker Desktop
installé, tout se fait depuis l'Explorateur de fichiers, dans le dossier `Ludifun` :

| Double-cliquer sur | Ce que ça fait |
|---|---|
| `Demarrer-Ludifun.bat` | lance Docker si besoin ; la première fois, demande quelle IA utiliser (colle ta clé Anthropic, ou IA factice) et propose la famille de démonstration ; démarre le serveur ; affiche **l'adresse à saisir sur le téléphone** et l'IA active |
| `Changer-IA-Ludifun.bat` | choisir l'IA : Claude, ChatGPT, Gemini, Mistral, Groq, Grok, un service compatible OpenAI (Azure OpenAI pour Copilot, OpenRouter, Ollama) ou l'IA factice ; coller la clé ; redémarrer |
| `Arreter-Ludifun.bat` | arrêter le serveur (les données sont gardées) |
| `Mettre-a-jour-Ludifun.bat` | récupérer la dernière version (`git pull`) et redémarrer |
| `Voir-les-erreurs-Ludifun.bat` | afficher l'état et les derniers messages du serveur, à envoyer en cas de problème |
| `Rapport-Ludifun.bat` | rapport de diagnostic (ordinateur, carte graphique, réglages sans les clés, appels à l'IA avec leurs durées et erreurs, Ollama) copié dans le presse-papiers : à coller dans la conversation avec Claude. Ni prénom, ni texte de leçon, ni clé |
| `Surveiller-Ludifun.bat` | à lancer **avant** un essai : note au fil de l'eau le journal du serveur (chaque appel à Ollama : chargement du modèle, jetons lus et écrits, vitesse, raison de l'arrêt ; éléments refusés ; erreurs, redémarrages), la charge du processeur et de la carte graphique et le modèle chargé par Ollama. Entrée pour finir : le fichier `surveillance-ludifun.txt` est copié, à coller dans la conversation avec Claude. Ni prénom, ni texte de leçon, ni clé |

Sur le téléphone, l'écran d'analyse a un bloc « Voir ce qui se passe » : chaque étape de l'IA
(modèle, durée, résultat) et, si l'analyse échoue, la raison en clair puis le message de l'IA.

Pendant une analyse, <http://localhost:8000/suivi> (dans le navigateur du PC) montre en direct
chaque appel à l'IA : l'étape, le modèle, depuis combien de temps, les durées moyennes par IA et
les dernières erreurs. Pratique pour comparer Ollama, Gemini et Claude.

La clé d'API est enregistrée dans le fichier `.env` du dossier : il reste sur le PC et n'est
jamais envoyé sur GitHub. La dépense d'IA est plafonnée à 5 $ par jour
(`LUDIFUN_AI_DAILY_BUDGET_USD` dans `.env`). Pour vérifier quelle IA est active, ouvrez
<http://localhost:8000/health/ready> : le nom de l'IA (`"ai":"claude"`, `"mistral"`…) ou `"ai":"fake"` pour l'IA factice.

Ensuite, passez directement au §3 (installer l'application). Les paragraphes suivants font la
même chose à la main (et sur macOS ou Linux).

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

Vérification : <http://localhost:8000/health/ready> doit afficher `"status":"ok"`, et `"ai"`
l'IA utilisée (`fake` ou `claude`).

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

1. Ouvrez https://github.com/Ricoudc/Ludifun/releases/tag/apk-test (connecté à votre compte
   GitHub). L'APK y est remplacé à chaque envoi de code ; la date et le commit sont indiqués.
2. Dans **Assets**, téléchargez **ludifun-test.apk**, directement sur le téléphone ou sur le PC
   puis envoyé au téléphone (câble USB, Google Drive, e-mail…).
3. Sur le téléphone, ouvrez le fichier et acceptez l'installation depuis cette source
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

**Le plus simple : Ollama**, gratuit, sur l'ordinateur. Rien ne sort de la maison.

1. Installez Ollama (<https://ollama.com/download>) et lancez-le.
2. Téléchargez un modèle qui sait lire les images : `ollama pull qwen2.5vl:7b` (environ 6 Go ;
   plus léger : `gemma3:4b`). Sous Windows, `Demarrer-Ludifun.bat` le propose.
3. Le serveur utilise Ollama par défaut. Dans l'application, **espace parent → Mon compte →
   Intelligence artificielle** : « Ollama (sur ce PC) » est proposé en premier et **vérifié
   aussitôt** : Ollama répond, le modèle est installé et sait lire les images, et une petite
   demande d'essai aboutit. Touchez un des modèles installés pour le choisir, puis « Enregistrer »
   (si l'IA ne fonctionne pas, l'application prévient avant d'enregistrer).

Sans carte graphique, l'analyse d'une leçon peut prendre plusieurs minutes. Le même écran
permet de choisir une IA en ligne (Claude, ChatGPT, Gemini, Mistral, Groq, Grok, Azure OpenAI
pour Copilot) avec sa clé : elle vaut pour toute la famille.

Choisir l'IA du serveur (celle des familles qui n'ont rien choisi) :

Sous Windows : `Changer-IA-Ludifun.bat`. Sinon, créez un fichier `.env` à la racine du dépôt
(il n'est jamais envoyé sur GitHub) :

```
LUDIFUN_AI_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...
LUDIFUN_AI_DAILY_BUDGET_USD=5
```

puis relancez `docker compose up -d` et vérifiez `"ai":"claude"` sur `/health/ready`. Les photos sont alors lues et analysées pour de vrai
(quelques secondes à quelques dizaines de secondes par leçon, avec un coût par analyse).

## En cas de problème

| Symptôme | Piste |
|---|---|
| « Serveur injoignable » | Même Wi-Fi ? Pas de VPN sur le téléphone ? Le pare-feu de l'ordinateur doit autoriser le port 8000 sur le réseau privé (Windows : autoriser Docker Desktop). Un Wi-Fi public ou d'entreprise peut isoler les appareils : essayez le partage de connexion du téléphone. |
| `/health/ready` répond `database_unavailable` | `docker compose ps` : la base doit être `healthy` ; sinon `docker compose up -d` à nouveau. |
| « Ollama injoignable » ou le test échoue | Ollama est-il lancé (icône près de l'horloge) ? Dans le navigateur du PC, <http://localhost:11434> doit afficher « Ollama is running ». Sinon, définissez la variable d'environnement Windows `OLLAMA_HOST=0.0.0.0`, relancez Ollama, puis `Demarrer-Ludifun.bat`. |
| L'analyse reste longtemps sur « Lecture de ta leçon… » (Ollama) | L'IA du PC travaille : sans carte graphique, une leçon peut demander 10 à 30 minutes (l'écran affiche le temps écoulé ; on peut fermer l'application). `Voir-les-erreurs-Ludifun.bat` montre l'avancement (« IA : lecture de la leçon terminée en 240 s »). Plus rapide : un modèle plus léger (`ollama pull qwen2.5vl:3b`, puis `Changer-IA-Ludifun.bat`), ou une IA en ligne choisie dans l'espace parent (Gemini et Groq ont une offre gratuite). |
| Ollama lent avec une carte graphique AMD | Pendant une analyse, `ollama ps` (ou `Voir-les-erreurs-Ludifun.bat`) indique où tourne le modèle : `100% GPU` va bien ; `CPU` signifie qu'Ollama n'utilise pas la carte. Mettez Ollama à jour ; les Radeon RX 6600/6700 ne sont pas toutes prises en charge sous Windows (selon la version, le moteur Vulkan s'active avec la variable d'environnement `OLLAMA_VULKAN=1`, puis redémarrage d'Ollama). Avec 8 Go de mémoire graphique, `qwen2.5vl:3b` tient entièrement sur la carte. |
| Ollama lent alors que la carte graphique est utilisée (moins de 15 jetons/s dans `Surveiller-Ludifun.bat`) | Le modèle déborde de la carte graphique dans la mémoire du PC : le Gestionnaire des tâches (Performance, GPU) montre la mémoire dédiée pleine et la mémoire partagée qui monte. Dans les réglages d'Ollama, « Context length » sur **4k** (Ludifun donne sa propre taille, 8192) ; dans une invite de commandes : `setx OLLAMA_FLASH_ATTENTION 1`, `setx OLLAMA_KV_CACHE_TYPE q8_0`, `setx OLLAMA_NUM_PARALLEL 1`, puis quitter et relancer Ollama. PC d'essai (RX 6600, 8 Go) : de 9 à 43 jetons/s. Modèles rangés sur un disque SSD : chargement plus rapide. |
| « modèle Ollama absent » | `ollama pull qwen2.5vl:7b` (ou le modèle choisi) dans un terminal. |
| Toute photo devient « La Révolution française » | C'est l'IA factice : `/health/ready` affiche `"ai":"fake"`. Voir §5 (Windows : `Changer-IA-Ludifun.bat`). Les leçons déjà analysées le restent : photographiez-les à nouveau. |
| Avec la vraie IA, « Petit souci » à l'analyse | Clé invalide ou sans crédit : `Voir-les-erreurs-Ludifun.bat` montre la raison (la clé n'y apparaît pas). Vérifiez la clé et le crédit sur console.anthropic.com. |
| `port is already allocated` au démarrage | Un autre serveur occupe le port (souvent une autre copie de Ludifun, par exemple un ZIP téléchargé à nouveau). `Demarrer-Ludifun.bat` arrête maintenant les autres copies et n'utilise plus le port 5432 ; gardez un seul dossier de Ludifun. Si le port 8000 est pris par un autre logiciel, fermez-le. |
| « Ce code ne marche pas » | Le code dure 10 minutes et ne sert qu'une fois : demandez-en un nouveau dans l'espace parent. |
| L'outil de démonstration refuse | Le compte existe déjà : ajoutez `--replace`. |
| Pas de `ludifun-test.apk` sur la page « apk-test » | L'APK de la dernière modification est en cours de fabrication (8 minutes environ) : onglet **Actions**, workflow **Mobile**. |

Limites de cette version de test : APK de débogage (plus lent qu'une version publiée), serveur
en HTTP sur le réseau local uniquement. Sur iPhone, il faut un Mac avec Xcode (`flutter run`).
La publication sur le Play Store en test fermé est l'étape 19.
