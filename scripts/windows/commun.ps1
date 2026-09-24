# Fonctions partagées par les scripts Windows de Ludifun (démarrer, arrêter, mettre à jour…).
# Rien ici n'envoie de donnée ailleurs que sur ce PC : le fichier .env reste local.

$ErrorActionPreference = 'Continue'
$Racine = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$FichierEnv = Join-Path $Racine '.env'
$UrlSante = 'http://localhost:8000/health/ready'
Set-Location $Racine

function Titre([string]$texte) {
    Write-Host ''
    Write-Host "=== $texte ===" -ForegroundColor Cyan
    Write-Host ''
}

function Etape([string]$texte) { Write-Host "-> $texte" -ForegroundColor Yellow }
function Ok([string]$texte) { Write-Host "OK  $texte" -ForegroundColor Green }

function Echec([string]$texte) {
    Write-Host ''
    Write-Host "ERREUR : $texte" -ForegroundColor Red
    Write-Host 'Envoie ce message (ou une capture de cette fenêtre) pour avoir de l''aide.'
    Read-Host 'Appuie sur Entrée pour fermer'
    exit 1
}

function Attendre-Fermeture {
    Write-Host ''
    Read-Host 'Appuie sur Entrée pour fermer cette fenêtre (le serveur continue de tourner)'
}

# --- Docker ---------------------------------------------------------------------------

function Docker-Pret {
    & docker info *> $null
    return $LASTEXITCODE -eq 0
}

function Assurer-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Echec 'Docker Desktop n''est pas installé : https://www.docker.com/products/docker-desktop'
    }
    if (Docker-Pret) { Ok 'Docker est prêt'; return }
    Etape 'Lancement de Docker Desktop (jusqu''à 3 minutes)…'
    $exe = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (Test-Path $exe) { Start-Process $exe }
    for ($i = 0; $i -lt 90; $i++) {
        Start-Sleep -Seconds 2
        if (Docker-Pret) { Ok 'Docker est prêt'; return }
    }
    Echec 'Docker ne répond pas. Ouvre Docker Desktop, attends la baleine verte, puis relance ce script.'
}

# --- Fichier .env (clé d'API, choix de l'IA) -------------------------------------------

function Lire-Env {
    $valeurs = [ordered]@{}
    if (Test-Path $FichierEnv) {
        foreach ($ligne in Get-Content $FichierEnv -Encoding UTF8) {
            $ligne = $ligne.TrimStart([char]0xFEFF)
            if ($ligne -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') { $valeurs[$Matches[1]] = $Matches[2].Trim() }
        }
    }
    return $valeurs
}

function Ecrire-Env($valeurs) {
    $lignes = @('# Réglages locaux de Ludifun : ce fichier reste sur ce PC (jamais envoyé sur GitHub).')
    foreach ($cle in $valeurs.Keys) { $lignes += "$cle=$($valeurs[$cle])" }
    # UTF-8 sans BOM : Docker Compose lit mal un fichier qui commence par un BOM.
    [System.IO.File]::WriteAllLines($FichierEnv, [string[]]$lignes, (New-Object System.Text.UTF8Encoding($false)))
}

function Choisir-IA {
    $valeurs = Lire-Env
    Write-Host ''
    Write-Host 'Quelle IA doit lire les photos et créer les jeux ?'
    Write-Host '  1. Claude (Anthropic) : la vraie analyse de tes leçons (clé d''API, payant à l''usage)'
    Write-Host '  2. IA factice : gratuite, toute photo devient une leçon d''exemple (pour découvrir)'
    $choix = Read-Host 'Tape 1 ou 2 puis Entrée'
    if ($choix -eq '2') {
        $valeurs['LUDIFUN_AI_PROVIDER'] = 'fake'
        Ecrire-Env $valeurs
        Ok 'IA factice choisie'
        return
    }
    $actuelle = $valeurs['ANTHROPIC_API_KEY']
    if ($actuelle) {
        $fin = $actuelle.Substring([Math]::Max(0, $actuelle.Length - 4))
        $garder = Read-Host "Une clé Anthropic est déjà enregistrée (…$fin). La garder ? (O/N)"
        if ($garder -match '^[nN]') { $actuelle = '' }
    }
    while (-not $actuelle) {
        Write-Host 'Colle ta clé d''API Anthropic (clic droit pour coller). Elle commence par sk-ant-'
        Write-Host '(Elle se crée sur https://console.anthropic.com → API Keys.)'
        $saisie = (Read-Host 'Clé').Trim()
        if ($saisie -like 'sk-ant-*') { $actuelle = $saisie } else { Write-Host 'Cette clé ne commence pas par sk-ant- : réessaie.' -ForegroundColor Red }
    }
    $valeurs['LUDIFUN_AI_PROVIDER'] = 'claude'
    $valeurs['ANTHROPIC_API_KEY'] = $actuelle
    if (-not $valeurs['LUDIFUN_AI_DAILY_BUDGET_USD']) { $valeurs['LUDIFUN_AI_DAILY_BUDGET_USD'] = '5' }
    Ecrire-Env $valeurs
    Ok "Claude choisi (dépense plafonnée à $($valeurs['LUDIFUN_AI_DAILY_BUDGET_USD']) `$ par jour, modifiable dans le fichier .env)"
}

function Assurer-Env {
    $valeurs = Lire-Env
    if (-not $valeurs['LUDIFUN_AI_PROVIDER']) { Choisir-IA }
}

# --- Serveur ---------------------------------------------------------------------------

function Attendre-Serveur {
    Etape 'Attente du serveur…'
    for ($i = 0; $i -lt 90; $i++) {
        try {
            $sante = Invoke-RestMethod -Uri $UrlSante -TimeoutSec 3
            if ($sante.status -eq 'ok') { return $sante }
        } catch { }
        Start-Sleep -Seconds 2
    }
    Echec 'Le serveur ne répond pas. Double-clique sur Voir-les-erreurs-Ludifun.bat et envoie le résultat.'
}

function Afficher-IA($sante) {
    if ($sante.ai -eq 'claude') {
        Ok 'IA : Claude (vraie analyse des photos)'
    } else {
        Write-Host 'IA : factice (toute photo devient une leçon d''exemple). Pour la vraie IA : Changer-IA-Ludifun.bat' -ForegroundColor Yellow
    }
}

function Adresses-PC {
    $exclues = 'vEthernet|WSL|Docker|Loopback|VirtualBox|VMware|Bluetooth'
    try {
        return @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.InterfaceAlias -notmatch $exclues } |
            ForEach-Object { $_.IPAddress })
    } catch { return @() }
}

function Afficher-Telephone {
    $adresses = Adresses-PC
    Write-Host ''
    Write-Host 'SUR LE TÉLÉPHONE (même Wi-Fi que ce PC) :' -ForegroundColor Cyan
    if ($adresses.Count -eq 0) {
        Write-Host '  Adresse du serveur : tape ipconfig dans PowerShell (ligne « Adresse IPv4 »), suivie de :8000'
    } else {
        foreach ($ip in $adresses) { Write-Host "  Adresse du serveur : $($ip):8000" -ForegroundColor Green }
        if ($adresses.Count -gt 1) { Write-Host '  (Plusieurs adresses : essaie la première, sinon la suivante.)' }
    }
    Write-Host '  Dans Ludifun : « Serveur de test » en bas du premier écran → saisir l''adresse → Tester → Enregistrer.'
}
