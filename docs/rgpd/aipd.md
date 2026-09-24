# Analyse d'impact relative à la protection des données (AIPD)

> **Brouillon (étape 19).** Une AIPD est requise : Ludifun traite des données d'enfants, qui
> sont des personnes vulnérables, et utilise l'intelligence artificielle (critères de la CNIL).
> Ce document décrit ce que fait le code aujourd'hui. Il doit être relu et validé par le
> responsable du traitement, qui peut s'aider de l'outil PIA de la CNIL, avant la bêta.

## 1. Description

Un enfant, sous le contrôle de son parent, photographie ou colle une leçon. Un modèle d'IA
(Anthropic) en extrait le texte, les notions et des exercices. L'application compose des
séances de révision et suit la maîtrise de chaque notion. Le parent consulte un tableau de bord.

Flux de données :
1. téléphone → API : photos (au plus 6 × 8 Mo), réponses, temps ;
2. API → Anthropic : photos, texte de la leçon, réponses rédigées, niveau scolaire ;
3. API → base de données (UE) : texte de la leçon, notions, résultats ; les photos sont
   effacées dès la lecture ;
4. API → fournisseur d'e-mails (UE) : adresse du parent et message de service.

## 2. Nécessité et proportionnalité

| Principe | Mise en œuvre |
|---|---|
| Minimisation | enfant : prénom ou pseudo, classe, avatar ; ni nom, ni date de naissance, ni e-mail. Parent : e-mail seulement (arbitrages A1 et A2 de la spécification technique). |
| Limitation des finalités | révision et suivi par le parent ; aucune publicité, aucun profilage commercial, aucun classement entre enfants |
| Conservation | photos non stockées ; comptes inactifs supprimés au bout de 12 mois (outil `app.tools.retention`) ; sauvegardes 30 jours |
| Consentement | case à cocher horodatée pour chaque profil d'enfant, en plus de la politique de confidentialité |
| Information | politique de confidentialité en langage clair (`/confidentialite`), lisible avant l'inscription |
| Droits | export JSON et suppression immédiate dans l'application ; page `/suppression-compte` ; contact |
| Sous-traitants | DPA avec chaque sous-traitant ; hébergement dans l'UE ; transfert vers Anthropic encadré |

## 3. Risques

| Risque | Origine | Gravité | Vraisemblance | Mesures | Risque résiduel |
|---|---|---|---|---|---|
| Accès illégitime aux résultats d'un enfant | vol d'un téléphone, d'un jeton ou d'un compte parent | importante | limitée | séparation parent/enfant et entre familles testée sur chaque route ; jetons hachés ; déliaison à distance ; rotation des jetons avec détection de réutilisation ; limites de débit | limité |
| Données personnelles dans la photo (nom sur le cahier, visage) | photo prise par l'enfant | importante | importante | photos jamais stockées ; la transcription exclut les en-têtes personnels ; conseil affiché avant la photo | limité, **à mesurer à l'étape 18** |
| Réutilisation des données par le fournisseur d'IA | transfert vers Anthropic | importante | négligeable | offre commerciale sans entraînement sur les données ; DPA ; aucun prénom transmis | négligeable |
| Contenu faux ou inadapté produit par l'IA | erreur du modèle | modérée | limitée | validations (citations obligatoires, règles), évaluation humaine (étape 18), avis des parents | limité |
| Perte de données | panne du serveur | modérée | limitée | sauvegardes chiffrées quotidiennes, restauration testée | limité |
| Conservation excessive | compte abandonné | modérée | importante | suppression automatique après 12 mois et prévenance | négligeable |
| Pression sur l'enfant | suivi trop détaillé par le parent | modérée | limitée | pas de classement ni de comparaison ; messages bienveillants ; pas de notifications insistantes | limité |

## 4. Plan d'action avant la bêta

- [ ] Signer les DPA (hébergeur, e-mails, Anthropic) et compléter le registre.
- [ ] Mesurer, sur les 30 leçons de l'étape 18, combien de transcriptions contiennent encore un
      nom propre de l'enfant ou de l'école. Si c'est trop fréquent, renforcer la consigne du prompt.
- [ ] Faire valider cette AIPD et la politique de confidentialité par le responsable du
      traitement (conseil juridique ou DPO).
- [ ] Réexaminer l'AIPD avant la bêta publique ou tout nouveau traitement (oral, V4).
