# Arrête Ludifun. Les données (comptes, leçons, résultats) sont gardées pour la prochaine fois.
. (Join-Path $PSScriptRoot 'commun.ps1')

Titre 'Arrêt de Ludifun'
Arreter-Moteur-Images
if (-not (Docker-Pret)) { Ok 'Docker est déjà arrêté : rien à faire.'; Attendre-Fermeture; exit 0 }
& docker compose down
if ($LASTEXITCODE -ne 0) { Echec 'L''arrêt n''a pas fonctionné.' }
Ok 'Ludifun est arrêté (tes données sont gardées).'
if ($DepuisMenu) { Read-Host 'Appuie sur Entrée pour revenir au menu' } else { Read-Host 'Appuie sur Entrée pour fermer' }
