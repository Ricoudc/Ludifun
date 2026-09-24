# Registre des activités de traitement (article 30 du RGPD)

> **Brouillon préparé à partir du code (étape 19)**, à relire et compléter par le responsable
> du traitement, idéalement avec un conseil juridique ou un DPO, avant la bêta. Les passages
> « À COMPLÉTER » dépendent de choix qui ne sont pas encore faits (société, fournisseurs).

| | |
|---|---|
| Responsable du traitement | À COMPLÉTER : nom, adresse, SIREN |
| Contact pour les données | À COMPLÉTER : adresse e-mail (aussi `LUDIFUN_CONTACT_EMAIL`) |
| Délégué à la protection des données | non obligatoire a priori ; à décider |
| Dernière mise à jour | 24/09/2026 |

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
| Données | prénom ou pseudo, classe, avatar ; texte des leçons (photos non conservées), notions, réponses, résultats, niveaux, types d'erreurs, temps de révision, XP et badges (sans classement entre enfants) ; objectifs fixés par le parent ; appareils liés (nom, dates) |
| Données exclues | nom de famille, date de naissance, e-mail, voix, localisation, identifiants publicitaires |
| Destinataires | le parent (tableau de bord, export) ; sous-traitants : hébergeur, Anthropic (texte et photos des leçons, réponses rédigées, sans prénom) |
| Transfert hors UE | Anthropic (États-Unis) : clauses contractuelles types, DPA ; À COMPLÉTER : vérifier la certification Data Privacy Framework au moment de la signature |
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
| Anthropic | lecture des leçons, analyse, correction des réponses rédigées | États-Unis | À COMPLÉTER (DPA commercial d'Anthropic) |
| Google (Play Store) | distribution de l'application | — | conditions du Play Store ; Ludifun n'y envoie aucune donnée |
