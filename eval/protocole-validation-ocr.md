# Évaluation OCR locale (photos de leçons)

Ce protocole complète les tests unitaires de `backend/tests/ai/test_tesseract.py`.
Il ne remplace pas une mesure sur des photos réelles : un test synthétique valide le
fonctionnement du code, pas la qualité sur les cahiers, photocopies et manuels des familles.

## Jeu d'essai privé

Conserver les photos et transcriptions de référence sur le PC de test. Ne pas ajouter
les photos de cahiers, noms d'élèves, annotations ou données personnelles au dépôt.

Structure locale conseillée :

```text
ocr-private/
  printed-clean/
    page-001.jpg
    page-001.txt
  printed-phone/
    page-002.jpg
    page-002.txt
  maths/
    page-003.jpg
    page-003.txt
  tables/
    page-004.jpg
    page-004.txt
  handwriting/
    page-005.jpg
    page-005.txt
```

Chaque fichier texte est la transcription de référence, fidèle à la page et dans l'ordre
de lecture. Anonymiser les images avant tout partage. Distinguer impérativement l'imprimé
de l'écriture manuscrite : les résultats ne doivent pas être agrégés sans ventilation.

## Cas à couvrir

- Imprimé propre, photocopie pâle, photo inclinée, ombre, reflet et flou.
- Titres, listes, colonnes, tableaux, encadrés et légendes.
- Dates, années, décimaux, fractions, unités et signes opératoires.
- Écriture manuscrite, évaluée séparément.
- Pages blanches, coupées, illisibles ou sans rapport avec une leçon.

## Mesures à reporter

| Mesure | Définition | Pourquoi |
|---|---|---|
| CER | distance d'édition caractères / nombre de caractères de référence | erreurs fines |
| WER | distance d'édition mots / nombre de mots de référence | lisibilité globale |
| Exactitude des tokens critiques | nombres, dates, fractions, unités et symboles exacts / total | une seule erreur peut changer un calcul ou une date |
| Fidélité de structure | ordre des blocs, titres, lignes et cellules conservés | éviter de mélanger les exercices |
| Latence | médiane et p95 par page, séparées à froid/à chaud | mesurer l'attente réelle |
| Relecture | pages reprises par vision, corrections utiles, régressions | vérifier le coût du mode auto |

Normaliser uniquement les différences typographiques sans effet sur le sens (Unicode,
espaces et fins de ligne). Ne pas normaliser les chiffres, signes, unités, accents ou
ordre des cellules pour masquer des erreurs.

## Comparaison à effectuer

Pour chaque page, conserver les résultats bruts et comparer :
1. Tesseract seul ;
2. le modèle vision seul ;
3. le mode `auto` (Tesseract puis relecture des pages ou passages douteux).

Relever les modèles et versions, langues Tesseract, réglages, date, matériel, temps et
erreurs. Une page n'est pas déclarée « bonne » uniquement sur sa confiance moyenne :
les passages importants à faible confiance déclenchent aussi la relecture.

## Porte de validation avant changement de défaut

Ne pas changer le moteur OCR par défaut, les modèles ni les réglages de production sur la
seule base des tests synthétiques ou de la CI. Le mode auto doit démontrer, sur le corpus
privé représentatif, qu'il réduit les erreurs critiques sans dégrader le CER/WER ni créer
une latence inacceptable. Publier dans la PR un tableau agrégé anonymisé, sans images ni
transcriptions privées.
