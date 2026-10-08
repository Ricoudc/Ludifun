# Récupère la dernière version de Ludifun (GitHub) et redémarre le serveur avec.
. (Join-Path $PSScriptRoot 'commun.ps1')

Titre 'Mise à jour de Ludifun'
if ((Get-Command git -ErrorAction SilentlyContinue) -and (Test-Path (Join-Path $Racine '.git'))) {
    Etape 'Téléchargement des nouveautés…'
    & git pull
    if ($LASTEXITCODE -ne 0) { Echec 'git pull n''a pas fonctionné (voir les messages au-dessus).' }
} else {
    Write-Host 'Ce dossier ne vient pas de git : télécharge à nouveau le ZIP depuis GitHub, décompresse-le,'
    Write-Host 'recopie ton fichier .env dedans, puis lance Demarrer-Ludifun.bat.' -ForegroundColor Yellow
    Attendre-Fermeture
    exit 0
}
Assurer-Docker
Arreter-Anciennes-Copies
Sauvegarde-Automatique
Etape 'Reconstruction et redémarrage du serveur (quelques minutes)…'
& docker compose up -d --build
if ($LASTEXITCODE -ne 0) { Echec 'docker compose n''a pas pu redémarrer le serveur.' }
Afficher-IA (Attendre-Serveur)
Write-Host ''
Write-Host 'Pense aussi à installer le nouvel APK sur le téléphone (GitHub → Actions → Mobile → Artifacts).'
Attendre-Fermeture
