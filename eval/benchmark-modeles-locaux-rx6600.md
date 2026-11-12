# Benchmark des modèles IA locaux — PC RX 6600 8 Go

## Objectif

Choisir un modèle local pour Ludifun sur le PC Windows 11 (Ryzen 5 5600X, 32 Go RAM,
Radeon RX 6600 8 Go), sans modifier le fournisseur utilisé en production et sans verser
de photos d'enfants dans le dépôt.

Le benchmark doit mesurer la qualité pédagogique **avant** la vitesse. Le corpus réel
reste local : `eval/lessons/` et `eval/results/` sont exclus de Git.

## Ce que le code sait déjà faire

- Le fournisseur `ollama` est déjà intégré via son API native.
- Les modèles peuvent être définis indépendamment par étape :
  `LUDIFUN_AI_OCR_MODEL`, `LUDIFUN_AI_ANALYSIS_MODEL`,
  `LUDIFUN_AI_MATERIAL_MODEL`, `LUDIFUN_AI_EVALUATION_MODEL`.
- Le lecteur peut utiliser `vision`, `tesseract` ou `auto`. Pour des cahiers manuscrits,
  conserver d'abord `vision` afin de comparer les modèles sur la même entrée.
- L'évaluateur existant mesure les leçons abouties, le rappel des notions attendues,
  les notions inventées, les éléments rejetés, les fuites de données personnelles, les
  questions ouvertes, la durée et les jetons/coûts.

Le rapport de benchmark enregistre maintenant aussi le modèle OCR : sans cette information,
on ne pouvait pas savoir quel modèle avait réellement lu les photos.

## Candidats à tester

Les tailles indiquées sont celles des téléchargements Ollama, pas une garantie de consommation
VRAM identique pendant l'inférence. Les résultats dépendent de la quantification, du contexte,
de la version Ollama et du pilote AMD.

| Profil | OCR | Analyse / matériel | Correction | Pourquoi |
|---|---|---|---|---|
| A — polyvalent prudent | `qwen3.5:4b` | `qwen3.5:4b` | `qwen3.5:4b` | Modèle vision + texte, candidat de départ pour 8 Go |
| B — vision spécialisée | `qwen3-vl:4b` | `qwen3.5:4b` | `qwen3.5:4b` | Compare la lecture photo sans imposer le VL à chaque étape |
| C — texte plus capable | `qwen3.5:4b` | `qwen3:8b` | `qwen3:4b` | Mesure le gain pédagogique éventuel et le coût de changement de modèle |
| D — référence actuelle | `qwen2.5vl:7b` | `qwen2.5vl:7b` | `qwen2.5vl:7b` | Point de comparaison avec le modèle déjà utilisé |

**Ne pas présumer que le profil C est plus rapide ou plus fiable** : les modèles de 8B peuvent
déborder de la VRAM disponible et le changement entre modèles peut entraîner des rechargements.
Garder une seule évaluation à la fois (`--concurrency 1`).

## Préparer le PC

Mettre Ollama à jour, puis télécharger les modèles à tester :

```powershell
ollama pull qwen3.5:4b
ollama pull qwen3-vl:4b
ollama pull qwen3:8b
ollama pull qwen3:4b
ollama pull qwen2.5vl:7b
ollama list
```

Vérifier d'abord qu'Ollama répond et que chaque modèle sait répondre. Pour les modèles vision,
faire aussi un essai avec une photo de test non personnelle :

```powershell
ollama run qwen3.5:4b
ollama run qwen3-vl:4b
```

La RX 6600 n'est pas listée parmi les cartes AMD ROCm officiellement prises en charge sous
Windows dans la documentation Ollama actuelle. Vulkan est une voie expérimentale/alternative :
il faut mesurer l'offload réel, pas se fier au seul pourcentage GPU affiché par le Gestionnaire
des tâches. Relever la version Ollama, le pilote AMD, le backend indiqué dans les journaux,
la VRAM dédiée et partagée.

## Exécuter les profils

Dans PowerShell, depuis la racine du dépôt, définir les variables puis lancer l'évaluateur.
Le corpus doit contenir les mêmes leçons annotées pour chaque profil.

### Profil A — polyvalent

```powershell
$env:LUDIFUN_AI_PROVIDER = "ollama"
$env:LUDIFUN_AI_OCR_MODEL = "qwen3.5:4b"
$env:LUDIFUN_AI_ANALYSIS_MODEL = "qwen3.5:4b"
$env:LUDIFUN_AI_MATERIAL_MODEL = "qwen3.5:4b"
$env:LUDIFUN_AI_EVALUATION_MODEL = "qwen3.5:4b"
$env:LUDIFUN_OLLAMA_NUM_CTX = "8192"
cd backend
uv run python -m app.tools.evaluate ../eval/lessons --concurrency 1 --out ../eval/results/qwen35-4b
```

### Profil B — vision spécialisée

```powershell
$env:LUDIFUN_AI_OCR_MODEL = "qwen3-vl:4b"
$env:LUDIFUN_AI_ANALYSIS_MODEL = "qwen3.5:4b"
$env:LUDIFUN_AI_MATERIAL_MODEL = "qwen3.5:4b"
$env:LUDIFUN_AI_EVALUATION_MODEL = "qwen3.5:4b"
uv run python -m app.tools.evaluate ../eval/lessons --concurrency 1 --out ../eval/results/qwen3vl4b
```

### Profil C — texte 8B

```powershell
$env:LUDIFUN_AI_OCR_MODEL = "qwen3.5:4b"
$env:LUDIFUN_AI_ANALYSIS_MODEL = "qwen3:8b"
$env:LUDIFUN_AI_MATERIAL_MODEL = "qwen3:8b"
$env:LUDIFUN_AI_EVALUATION_MODEL = "qwen3:4b"
uv run python -m app.tools.evaluate ../eval/lessons --concurrency 1 --out ../eval/results/qwen3-8b-mix
```

### Profil D — référence actuelle

```powershell
$env:LUDIFUN_AI_OCR_MODEL = "qwen2.5vl:7b"
$env:LUDIFUN_AI_ANALYSIS_MODEL = "qwen2.5vl:7b"
$env:LUDIFUN_AI_MATERIAL_MODEL = "qwen2.5vl:7b"
$env:LUDIFUN_AI_EVALUATION_MODEL = "qwen2.5vl:7b"
uv run python -m app.tools.evaluate ../eval/lessons --concurrency 1 --out ../eval/results/qwen25vl7b
```

Chaque commande crée un sous-dossier horodaté sous le dossier `--out`. Vérifier le fichier
`metrics.json` : les modèles OCR, analyse, matériel et correction doivent tous être présents.
Les variables de la session PowerShell peuvent être effacées avec
`Get-ChildItem Env:LUDIFUN_AI_*` puis `Remove-Item Env:LUDIFUN_AI_*` après le test.

## Mesures obligatoires

1. **Qualité** : leçons traitées, matière/niveau corrects, rappel des notions indispensables,
   notions inventées, éléments rejetés et passages à faire vérifier.
2. **Pédagogie** : relire les questions ouvertes et leurs réponses modèles avec la grille humaine ;
   vérifier la justesse, l'adaptation au niveau, l'absence de réponse révélée dans la question,
   la clarté des explications et la pertinence des indices.
3. **Vie privée** : zéro nom d'enfant, d'école ou d'enseignant reproduit dans le texte OCR.
4. **Performance** : durée totale et par étape, temps de chargement, prompt processing,
   génération (tokens/s), VRAM dédiée/partagée, RAM, erreurs, reprises et sorties tronquées.
5. **Stabilité** : refaire chaque profil au moins deux fois sur un sous-ensemble identique ;
   noter les échecs et la variabilité.

Le benchmark existant mesure la justesse de lecture et d'analyse ; la pertinence pédagogique
des questions ouvertes exige une annotation humaine. Ne pas convertir un score lexical en
« vérité pédagogique ».

## Règle de décision

- Écarter tout profil qui perd des notions indispensables, invente des faits, expose des données
  personnelles ou produit des explications erronées.
- Parmi les profils restants, choisir celui qui a le meilleur compromis entre pertinence
  pédagogique, stabilité et latence réelle.
- Si le modèle 4B est trop faible pédagogiquement, garder le modèle cloud/Groq/Claude comme
  secours ou pour les tâches difficiles ; ne pas augmenter aveuglément la taille locale.
- Ne pas changer les modèles par défaut dans `presets.py` avant d'avoir les résultats du corpus
  réel et une revue humaine.

## Limite de cet audit

Le dépôt et les tests automatisés peuvent être examinés à distance, mais les performances GPU
ne peuvent pas être mesurées depuis GitHub. Il faut exécuter ces commandes sur le PC Windows
réel avec le corpus privé local. Aucun résultat de tokens/s ou de qualité n'est présumé ici.
