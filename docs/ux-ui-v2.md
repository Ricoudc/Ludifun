# Ludifun V2 — direction UX/UI

## Intention
Faire évoluer l'application vers une expérience d'apprentissage chaleureuse, claire et motivante. Le langage visuel combine une base premium et apaisante avec des accents ludiques : bleu confiance, turquoise progression, jaune récompense, corail énergie.

## Principes
1. Une action principale évidente par écran.
2. Hiérarchie typographique forte et texte adapté aux jeunes lecteurs.
3. Grandes zones tactiles, espacements réguliers et contrastes accessibles.
4. Les récompenses valorisent l'effort, la persévérance et la progression — jamais la vitesse seule.
5. L'interface enfant reste distincte de l'espace parent, plus sobre et orienté données.
6. Les animations et sons restent facultatifs, courts et non bloquants.
7. Les états chargement, vide, erreur et hors-ligne sont conçus explicitement.

## Palette
| Rôle | Couleur |
|---|---|
| Primaire | #356FC8 |
| Fond | #F6F8FC |
| Texte | #20304A |
| Turquoise | #35A995 |
| Jaune | #FFC857 |
| Corail | #E98567 |
| Réussite | #269B78 |

## Première tranche
- Thème Material 3 harmonisé : palette, typographie, boutons, champs, cartes, puces et snackbars.
- Accueil enfant : carte d'accueil illustrée et trois actions sous forme de tuiles descriptives.
- Routes, providers, API, états hors-ligne et logique de progression conservés.
- Aucun changement de logique métier ni dépendance ajoutée.

## Suite
1. Appliquer le système aux écrans d'exercice et aux bilans.
2. Reconcevoir l'accueil parent et les tableaux de bord avec les données disponibles.
3. Créer une mascotte illustrée propriétaire et ses expressions après validation graphique.
4. Tester tailles d'écran, contraste, TalkBack/VoiceOver et parcours enfant.

## Garde-fous
Cette première tranche est une refonte visuelle progressive, pas une validation d'accessibilité ni une refonte complète. Les tests Flutter et l'analyse statique doivent être exécutés dans CI avant intégration.
