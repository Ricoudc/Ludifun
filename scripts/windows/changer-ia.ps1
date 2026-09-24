# Change l'IA utilisée (Claude avec une clé d'API, ou IA factice) puis redémarre le serveur.
. (Join-Path $PSScriptRoot 'commun.ps1')

Titre 'Choix de l''IA de Ludifun'
Choisir-IA
Assurer-Docker
Etape 'Redémarrage du serveur avec ce réglage…'
& docker compose up -d
if ($LASTEXITCODE -ne 0) { Echec 'Le redémarrage n''a pas fonctionné.' }
Afficher-IA (Attendre-Serveur)
Attendre-Fermeture
