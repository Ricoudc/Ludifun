# Affiche l'état du serveur et ses derniers messages, pour comprendre un problème.
. (Join-Path $PSScriptRoot 'commun.ps1')

Titre 'État de Ludifun'
if (-not (Docker-Pret)) { Echec 'Docker n''est pas lancé : ouvre Docker Desktop.' }
& docker compose ps -a
Titre 'Derniers messages du serveur (api)'
& docker compose logs api --tail 80
Titre 'Derniers messages de la base (db)'
& docker compose logs db --tail 20
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Titre 'Ollama : modèles chargés (colonne PROCESSOR : GPU = carte graphique, CPU = processeur, lent)'
    & ollama ps
}
Write-Host ''
Write-Host 'La clé d''API n''apparaît jamais ici. Tu peux copier ce texte pour demander de l''aide.'
Read-Host 'Appuie sur Entrée pour fermer'
