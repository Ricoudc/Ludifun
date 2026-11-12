# Registre des activités de traitement (article 30 du RGPD)

> **Brouillon préparé à partir du code (étape 19)**, à relire et compléter par le responsable
> du traitement, idéalement avec un conseil juridique ou un DPO, avant la bêta. Les passages
> « À COMPLÉTER » dépendent de choix qui ne sont pas encore faits (société, fournisseurs).

| | |
|---|---|
| Responsable du traitement | À COMPLÉTER : nom, adresse, SIREN |
| Contact pour les données | À COMPLÉTER : adresse e-mail (aussi `LUDIFUN_CONTACT_EMAIL`) |
| Délégué à la protection des données | non obligatoire a priori ; à décider |
| Dernière mise à jour | 09/11/2026 (fournisseurs d'IA au choix, images, voix, exercices sur les erreurs) |

## Traitement 1 : compte parent

| Rubrique | Contenu |
|---|---|
| Finalité | créer et sécuriser le compte ; mot de passe oublié ; confirmation de l'adresse ; messages de service (prévenance avant suppression) |
| Base légale | exécution du contrat (conditions d'utilisation) |
| Personnes concernées | parents |
| Données | e-mail, prénom facultatif, mot de passe haché (argon2id), IA choisie pour la famille et sa clé d'API (chiffrée), dates d'acceptation de la politique, de confirmation de l'e-mail, de dernière connexion ; jetons de session hachés |
| Destinataires | équipe Ludifun (support) ; sous-traitants : hébergeur, fournisseur d'e-mails |
| Durée | jusqu'à la suppression du compte, ou 12 mois d'inactivité (prévenance 30 jours avant) ; jetons : 30 jours |
| Sécurité | HTTPS, HSTS, hachage, rotation des jetons, limites de débit, séparation des espaces |

## Traitement 2 : profils des enfants et révisions

| Rubrique | Contenu |
|---|---|
| Finalité | composer des séances de révision adaptées, suivre les progrès, tableau de bord du parent, objectifs et contrôles |
| Base légale | consentement du titulaire de l'autorité parentale (enfant de moins de 15 ans, article 45 de la loi Informatique et Libertés), recueilli et horodaté pour chaque profil |
| Personnes concernées | enfants du CP à la 3e (6 à 15 ans) |
| Données | prénom ou pseudo, classe, avatar ; texte des leçons (photos non conservées), leçon relue et corrigée par le parent avant l'enfant, notions, réponses, résultats, niveaux, types d'erreurs, aides demandées (« Je n'ai pas compris », avec l'heure), questions signalées (🚩, raison choisie dans une liste, sans texte libre), exercices du mode devoirs (énoncé lu, étapes vues, réponses essayées ; photo non conservée), temps de révision, XP et badges (sans classement entre enfants) ; explications données à Ludi dans « Enseigne-moi » ; exercices neufs créés sur une erreur qui revient (notion et type d'erreur, sans prénom) ; profil par notion et conseils de la semaine (calculés, jamais envoyés à l'IA) ; objectifs fixés par le parent ; appareils liés (nom, dates) |
| Données exclues | nom de famille, date de naissance, e-mail, voix (« Dire ma réponse » : reconnue sur le téléphone, jamais envoyée ni enregistrée ; seul le texte reconnu, corrigeable, part comme une réponse écrite), localisation, identifiants publicitaires |
| Destinataires | le parent (tableau de bord, export) ; sous-traitants : hébergeur, **l'IA choisie par la famille** (voir « Fournisseurs d'IA » ci-dessous : photos et texte des leçons, réponses rédigées, explications d'« Enseigne-moi », énoncés du mode devoirs, notion et type d'erreur pour un exercice neuf ; jamais le prénom) ; si le parent l'a permis, ses autres IA déjà réglées quand la première ne répond pas (§147) ; service d'images éventuel (seulement une description en anglais d'une chose concrète, écrite à partir de la leçon et contrôlée par le code : ni prénom, ni texte de leçon) ; si le parent permet les sites éducatifs de confiance : titre de la leçon et noms des notions envoyés aux sites (Vikidia, catalogue MathALÉA, moteur de recherche du serveur), et l'appareil de l'enfant ouvre directement coopmaths.fr, vikidia.org ou lumni.fr dans l'application (adresse IP, cookies de ces sites ; À COMPLÉTER : vérifier leurs politiques) |
| Transfert hors UE | selon l'IA choisie : aucun (Ollama sur le PC de la famille, Mistral), ou États-Unis (Anthropic, OpenAI, Google, Groq, xAI, Microsoft Azure selon la région choisie) : clauses contractuelles types, DPA ; À COMPLÉTER : vérifier, pour chaque fournisseur proposé, la certification Data Privacy Framework et l'absence d'entraînement sur les données au moment de la signature |
| Durée | jusqu'à la suppression par le parent (leçon, profil, compte), ou 12 mois d'inactivité du compte ; photos : effacées dès la lecture |
| Droits | accès et portabilité (export JSON dans l'application), effacement (dans l'application), rectification (profil), retrait du consentement (suppression du profil) |

## Traitement 3 : avis et mesure de l'usage (bêta)

| Rubrique | Contenu |
|---|---|
| Finalité | améliorer l'application pendant la bêta : avis envoyés depuis l'application, indicateurs agrégés (`app.tools.pilot_report`) |
| Base légale | intérêt légitime (améliorer le service) ; l'avis est facultatif |
| Données | note, message, écran, séance concernée ; indicateurs agrégés sans prénom ni texte de leçon |
| Destinataires | équipe Ludifun |
| Durée | avis : supprimés avec leur auteur ; rapports : gardés hors du dépôt, supprimés après la bêta |

## Traitement 4 : sécurité et exploitation

| Rubrique | Contenu |
|---|---|
| Finalité | sécurité, diagnostic des pannes, plafond de dépense IA |
| Base légale | intérêt légitime |
| Données | journaux techniques (adresse IP, route, code de réponse, durée ; ni contenu de leçon, ni jeton), journal des appels IA (modèle, jetons consommés, durée, coût) |
| Durée | journaux : bornés en taille (quelques jours, 30 jours au plus) ; sauvegardes chiffrées : 30 jours |

## Sous-traitants

| Sous-traitant | Rôle | Lieu | DPA |
|---|---|---|---|
| À COMPLÉTER (hébergeur) | serveur, base de données, sauvegardes | UE | À COMPLÉTER |
| À COMPLÉTER (e-mails) | envoi des e-mails de service | UE | À COMPLÉTER |
| Anthropic (Claude) | IA du serveur par défaut, ou choisie par la famille : lecture des leçons, analyse, exercices, correction des réponses rédigées, « Enseigne-moi », exercices sur une erreur | États-Unis | À COMPLÉTER (DPA commercial d'Anthropic) |
| OpenAI, Google (Gemini), Groq, xAI (Grok), Microsoft (Azure OpenAI) ou autre service compatible | les mêmes rôles, **seulement si la famille le choisit** avec sa propre clé (espace parent) | États-Unis (Azure : selon la région) | la famille accepte les conditions du fournisseur ; À COMPLÉTER : liste des fournisseurs proposés et leurs DPA. Gemini : l'offre gratuite peut réutiliser les données, l'application le dit au parent au moment du choix |
| Mistral | les mêmes rôles, si la famille le choisit | UE (France) | À COMPLÉTER |
| — (Ollama, Tesseract) | IA et lecture des photos installées sur le PC de la famille ou sur le serveur : rien ne part chez un tiers | sur place | sans objet |
| Pollinations ou Cloudflare Workers AI (facultatif) | dessin des images des notions concrètes, si le serveur l'a réglé : reçoit seulement une description en anglais contrôlée par le code | États-Unis | À COMPLÉTER ; sinon images dessinées sur le PC (stable-diffusion.cpp, ComfyUI) ou pas d'images |
| Google (Play Store) | distribution de l'application | — | conditions du Play Store ; Ludifun n'y envoie aucune donnée |
