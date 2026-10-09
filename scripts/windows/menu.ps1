# Menu de Ludifun.bat : toutes les actions au même endroit (démarrer, mettre à jour, choisir
# l'IA, sauvegarder…). Chaque action tourne dans sa propre fenêtre PowerShell, puis on revient
# ici. Code de sortie 3 : relancer le menu (après une mise à jour, pour prendre le nouveau).
. (Join-Path $PSScriptRoot 'commun.ps1')

$Actions = [ordered]@{
    '1'  = @('Démarrer Ludifun', 'demarrer.ps1')
    '2'  = @('Arrêter Ludifun', 'arreter.ps1')
    '3'  = @('Mettre à jour (serveur et application du téléphone)', 'mettre-a-jour.ps1')
    '4'  = @('Choisir l''IA', 'changer-ia.ps1')
    '5'  = @('Sauvegarder les données maintenant', 'sauvegarder.ps1')
    '6'  = @('Remettre une sauvegarde', 'restaurer.ps1')
    '7'  = @('Recherche sur les sites éducatifs de confiance', 'activer-recherche.ps1')
    '8'  = @('Installer le moteur d''images (facultatif)', 'installer-images.ps1')
    '9'  = @('Voir les erreurs du serveur', 'erreurs.ps1')
    '10' = @('Rapport de diagnostic (à envoyer en cas de problème)', 'rapport.ps1')
    '11' = @('Surveiller un essai (à lancer avant)', 'surveiller.ps1')
    '12' = @('Créer un raccourci « Ludifun » sur le Bureau', '')
}

function Serveur-Demarre {
    try { return (Invoke-RestMethod -Uri $UrlSante -TimeoutSec 2).status -eq 'ok' } catch { return $false }
}

function Creer-Raccourci {
    $bureau = [Environment]::GetFolderPath('Desktop')
    $coquille = New-Object -ComObject WScript.Shell
    $raccourci = $coquille.CreateShortcut((Join-Path $bureau 'Ludifun.lnk'))
    $raccourci.TargetPath = Join-Path $Racine 'Ludifun.bat'
    $raccourci.WorkingDirectory = $Racine
    $raccourci.Description = 'Ludifun : démarrer, mettre à jour, réglages'
    $raccourci.Save()
    Ok 'Raccourci « Ludifun » créé sur le Bureau.'
    Start-Sleep -Seconds 2
}

$env:LUDIFUN_MENU = '1'
$powershell = (Get-Process -Id $PID).Path
Write-Host 'Recherche d''une nouvelle version…' -ForegroundColor DarkGray
$nouveaute = Mise-A-Jour-Disponible

while ($true) {
    Clear-Host
    $demarre = Serveur-Demarre
    Titre 'Ludifun'
    if ($demarre) {
        Ok 'Le serveur tourne.'
        foreach ($ip in Adresses-PC) { Write-Host "    Adresse à saisir sur le téléphone : $($ip):8000" -ForegroundColor Green }
    } else {
        Write-Host 'Le serveur est arrêté.' -ForegroundColor Yellow
    }
    if ($nouveaute) { Write-Host '>>> Une nouvelle version de Ludifun est disponible : choix 3.' -ForegroundColor Magenta }
    Write-Host ''
    foreach ($numero in $Actions.Keys) { Write-Host ('  {0,2}. {1}' -f $numero, $Actions[$numero][0]) }
    Write-Host '   0. Quitter (le serveur continue de tourner)'
    Write-Host ''
    $defaut = if ($demarre) { '0' } else { '1' }
    $choix = (Read-Host "Ton choix puis Entrée (Entrée seule : $defaut)").Trim()
    if (-not $choix) { $choix = $defaut }
    if ($choix -eq '0') { exit 0 }
    if (-not $Actions.Contains($choix)) { continue }
    if ($choix -eq '12') { Creer-Raccourci; continue }
    Clear-Host
    & $powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot $Actions[$choix][1])
    if ($choix -eq '3') { exit 3 }  # nouvelle version : le menu se relance avec elle
}
