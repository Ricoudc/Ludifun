# Remet une sauvegarde de Ludifun : tout ce qui a été fait depuis est remplacé. La base actuelle
# est d'abord sauvegardée (« avant-restauration ») : on peut revenir en arrière.
. (Join-Path $PSScriptRoot 'commun.ps1')

Titre 'Restaurer une sauvegarde de Ludifun'
$liste = @(Get-ChildItem $DossierSauvegardes -Filter 'ludifun-*.dump' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending)
if ($liste.Count -eq 0) { Echec "Aucune sauvegarde dans $DossierSauvegardes." }
for ($i = 0; $i -lt $liste.Count; $i++) {
    $f = $liste[$i]
    Write-Host ('{0,2}. {1:dd/MM/yyyy HH:mm}  {2,6} Ko  {3}' -f ($i + 1), $f.LastWriteTime, [math]::Ceiling($f.Length / 1KB), $f.Name)
}
Write-Host ''
$choix = Read-Host 'Numéro de la sauvegarde à remettre (Entrée pour annuler)'
if (-not $choix) { Ok 'Rien n''a été changé.'; Attendre-Fermeture; exit 0 }
$numero = 0
if (-not [int]::TryParse($choix, [ref]$numero) -or $numero -lt 1 -or $numero -gt $liste.Count) {
    Echec "« $choix » n'est pas dans la liste."
}
$fichier = $liste[$numero - 1]
Write-Host ''
Write-Host "Ludifun va revenir au $('{0:dd/MM/yyyy à HH:mm}' -f $fichier.LastWriteTime)." -ForegroundColor Yellow
Write-Host 'Ce qui a été fait depuis (leçons, séances, comptes) sera remplacé.' -ForegroundColor Yellow
$ok = Read-Host 'Tape OUI pour confirmer'
if ($ok -ne 'OUI') { Ok 'Rien n''a été changé.'; Attendre-Fermeture; exit 0 }

Assurer-Docker
Arreter-Anciennes-Copies
Etape 'Sauvegarde de la base actuelle, au cas où…'
$avant = Sauvegarder-Base 'avant-restauration'
if (-not $avant) { Echec 'La base actuelle n''a pas pu être sauvegardée : rien n''a été changé.' }
Ok "Base actuelle gardée : $avant"
Etape 'Restauration…'
$erreur = Restaurer-Base $fichier.FullName
if ($erreur) {
    & docker compose up -d *> $null
    Echec $erreur
}
Ok 'Sauvegarde remise'
Etape 'Redémarrage du serveur…'
& docker compose up -d
if ($LASTEXITCODE -ne 0) { Echec 'docker compose n''a pas pu redémarrer le serveur.' }
Afficher-IA (Attendre-Serveur)
Ok 'Ludifun est revenu à cette sauvegarde.'
Attendre-Fermeture
