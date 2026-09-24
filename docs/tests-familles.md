# Tests avec de vraies familles (étape 18)

But : vérifier sur **30 vraies leçons** et avec **5 enfants et leurs parents** que Ludifun fait
réviser ce qui sera demandé en classe, sans erreur, et que les enfants s'en servent seuls. Les
critères de passage sont ceux du cahier des charges V1 (§17.3), rappelés au §5.

Deux volets, dans cet ordre :

1. **Relecture par un adulte** des séances produites pour les 30 leçons : outil
   `app.tools.evaluate` et grille [`eval/grille-evaluation.md`](../eval/grille-evaluation.md) (A).
2. **Deux semaines d'usage réel** par 5 familles, avec l'application sur leur téléphone ou leur
   tablette : observation de la première séance (grille, partie B), avis dans l'application,
   rapport `app.tools.pilot_report`.

## 1. Avant de commencer

| Quoi | Où | Qui |
|---|---|---|
| Clé API Anthropic et budget IA du jour (`LUDIFUN_AI_DAILY_BUDGET_USD`) | `backend/.env`, jamais dans git | responsable technique |
| Serveur joignable par les téléphones (même Wi-Fi, ou hébergement de test) | [`tester-sur-telephone.md`](tester-sur-telephone.md) | responsable technique |
| Application installée (APK de test) | [`tester-sur-telephone.md`](tester-sur-telephone.md) | chaque famille |
| 30 leçons photographiées, noms masqués | `eval/lessons/` (hors git) | familles et enseignant |
| Accord écrit de chaque parent (ci-dessous) | papier ou e-mail, conservé hors du dépôt | coordinateur |

Répartition conseillée des 30 leçons (§17.1 V1) : CP à 3e, au moins 4 matières, des cahiers
manuscrits, des pages de manuel et des photocopies, 1 ou 2 photos qui ne sont pas des leçons.

## 2. Accord des familles

À faire signer (ou accepter par e-mail) par un parent, avant toute photo :

> Pendant deux semaines, mon enfant utilise Ludifun, une application de révision encore en
> test. J'accepte que :
> - les photos de ses leçons soient lues par un service d'IA (Anthropic) pour préparer les
>   révisions ; les photos ne sont pas conservées par Ludifun, seul le texte de la leçon l'est ;
> - ses réponses et ses résultats servent à mesurer si l'application est utile, sous forme de
>   chiffres anonymes (« Enfant 1, CM1 ») ;
> - quelqu'un de l'équipe observe sa première séance, sans l'aider.
>
> Je peux arrêter à tout moment : je supprime le profil de mon enfant ou mon compte depuis
> l'application, et toutes ses données sont effacées, avis compris.

Dans l'application, le parent crée lui-même son compte et le profil de l'enfant ; la case
d'accord parental reste obligatoire. Aucun nom de famille n'est demandé.

## 3. Déroulé sur deux semaines

| Jour | Quoi | Outil |
|---|---|---|
| J-7 à J-1 | Relecture des 30 leçons par un adulte : pertinence, justesse, clarté, plaisir | `uv run python -m app.tools.evaluate ../eval/lessons`, grille A |
| J-1 | Si la justesse est sous le seuil : corriger les prompts, relancer la relecture | [`eval/README.md`](../eval/README.md) |
| J0 | Installation chez chaque famille ; le parent crée le compte, ajoute l'enfant, lie son appareil | parcours parent |
| J0 | **Première séance observée** : l'enfant photographie une leçon et révise seul ; l'observateur remplit la grille B | grille B |
| J1 à J13 | Usage libre : l'enfant révise quand il veut ; le parent peut fixer un temps par jour ou un contrôle | objectifs du parent |
| J7 | Point d'étape : rapport intermédiaire, messages des parents, blocages | `pilot_report` |
| J14 | Entretien de 15 minutes avec chaque parent et chaque enfant ; rapport final | `pilot_report`, questions §4 |

Consignes à l'observateur : ne répondre qu'aux questions sur l'utilisation de l'application,
jamais sur le contenu. Noter mot pour mot ce que dit l'enfant quand il hésite.

## 4. Ce que l'on recueille

**Dans l'application** (rien à faire de plus pour les familles) :

- à la fin de chaque séance, l'enfant peut dire s'il a aimé : 😕, 🙂 ou 😍 (un toucher,
  facultatif) ;
- le parent peut écrire à tout moment dans *Mon compte → Donner mon avis* (une note de 1 à 5
  et/ou un message) ;
- les séances elles-mêmes : durée, aides demandées, remédiations, pauses proposées, défis bonus,
  types d'erreurs.

**Par le rapport**, depuis `backend/`, là où la base est joignable :

```bash
uv run python -m app.tools.pilot_report --since 2026-10-05 --until 2026-10-18 \
    --out ../eval/results/pilote-final.md
```

Le rapport ne contient ni prénom ni texte de leçon : les enfants sont numérotés (« Enfant 1
(CM1) »), seuls les messages écrits par les parents sont cités. Il reste dans `eval/results/`,
exclu de git.

| Rubrique | Contenu |
|---|---|
| Critères de passage | enfants qui finissent leurs séances sans aide, séances terminées, leçons analysées sans échec, avis des enfants et des parents |
| Par enfant | séances, terminées, sans aide, minutes, note moyenne, avis |
| Séances | durée réelle et prévue, part des activités avec « Je n'ai pas compris », remédiations, pauses, défis bonus, erreurs les plus fréquentes |
| Leçons et IA | sources (photo ou texte), échecs par cause, leçons à vérifier, temps et coût d'IA par leçon, corrections des réponses rédigées (IA ou mots clés), notions maîtrisées |
| Messages des parents | datés, avec la note |

**Questions de l'entretien final**

- Enfant : « Qu'est-ce que tu as préféré ? », « Qu'est-ce qui était difficile ou bizarre ? »,
  « Tu voudrais réviser comme ça la prochaine fois ? »
- Parent : « Les questions correspondaient-elles à ce qui a été demandé en classe ? »,
  « Avez-vous vu une erreur de contenu ? », « Qu'est-ce qui vous a manqué pour suivre votre
  enfant ? », « Combien seriez-vous prêt à payer, et sous quelle forme ? »

## 5. Critères de passage

| Critère | Seuil | Source |
|---|---|---|
| Pertinence des séances | ≥ 4 / 5 en moyenne | grille A |
| Justesse du contenu | 5 / 5 sur 90 % des séances | grille A, messages des parents |
| Enfants autonomes | 4 enfants sur 5 finissent leurs séances sans aide | grille B (première séance), rapport (séances sans « Je n'ai pas compris ») |
| Séances terminées | ≥ 80 % | rapport |
| Leçons analysées sans échec (photos de leçons) | ≥ 90 % | rapport |
| Plaisir | avis des enfants ≥ 4 / 5 | rapport, grille A |

Si un critère n'est pas atteint : noter la cause (prompt, écran, consigne, photo), corriger,
et refaire le volet concerné avant la bêta Android (étape 19).

## 6. Après les tests

- Supprimer `eval/lessons/` et les rapports bruts quand les corrections sont faites ; garder
  uniquement les chiffres agrégés.
- Proposer aux familles de garder leur compte pour la bêta, ou de le supprimer depuis
  l'application (tout est effacé, avis compris).
- Reporter les résultats dans la spécification technique (§9, étape 18) et les décisions en
  attente (A1 à A3, A9).
