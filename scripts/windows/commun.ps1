# Fonctions partagées par les scripts Windows de Ludifun (démarrer, arrêter, mettre à jour…).
# Rien ici n'envoie de donnée ailleurs que sur ce PC : le fichier .env reste local.

$ErrorActionPreference = 'Continue'
$Racine = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$FichierEnv = Join-Path $Racine '.env'
# Copie des réglages dans le profil Windows : un nouveau dossier de Ludifun (ZIP téléchargé à
# nouveau) reprend la même IA, la même clé et surtout les mêmes secrets. Sans eux, la base
# (gardée par Docker) ne pourrait plus lire les clés d'IA enregistrées par les familles.
$EnvCommun = Join-Path $env:LOCALAPPDATA 'Ludifun\reglages.env'
$UrlSante = 'http://localhost:8000/health/ready'
Set-Location $Racine
# Les scripts n'ont pas besoin d'accéder à la base depuis Windows : un port peu utilisé évite le
# conflit avec un PostgreSQL installé sur le PC (« port is already allocated »).
if (-not $env:LUDIFUN_DB_PORT) { $env:LUDIFUN_DB_PORT = '55432' }

function Titre([string]$texte) {
    Write-Host ''
    Write-Host "=== $texte ===" -ForegroundColor Cyan
    Write-Host ''
}

function Etape([string]$texte) { Write-Host "-> $texte" -ForegroundColor Yellow }
function Ok([string]$texte) { Write-Host "OK  $texte" -ForegroundColor Green }

# Lancé depuis le menu de Ludifun.bat : on revient au menu au lieu de fermer la fenêtre.
$DepuisMenu = $env:LUDIFUN_MENU -eq '1'

# Où trouver une action, pour les messages : tout passe par Ludifun.bat.
function Choix([int]$numero) { return "Ludifun.bat, choix $numero" }

function Echec([string]$texte) {
    Write-Host ''
    Write-Host "ERREUR : $texte" -ForegroundColor Red
    Write-Host 'Envoie ce message (ou une capture de cette fenêtre) pour avoir de l''aide.'
    if ($DepuisMenu) { Read-Host 'Appuie sur Entrée pour revenir au menu' } else { Read-Host 'Appuie sur Entrée pour fermer' }
    exit 1
}

function Attendre-Fermeture {
    Write-Host ''
    if ($DepuisMenu) { Read-Host 'Appuie sur Entrée pour revenir au menu'; return }
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

# Un autre dossier de Ludifun (ZIP téléchargé à nouveau, ancienne version…) a pu laisser tourner
# son serveur sous un autre nom : il occuperait les ports. On l'arrête ; les données restent.
function Arreter-Anciennes-Copies {
    $projets = & docker ps -a --filter 'label=com.docker.compose.project' --format '{{.Label "com.docker.compose.project"}}' 2>$null |
        Sort-Object -Unique | Where-Object { $_ -like 'ludifun*' -and $_ -ne 'ludifun' }
    foreach ($projet in $projets) {
        Etape "Arrêt d'une autre copie de Ludifun ($projet)…"
        & docker compose -p $projet down *> $null
    }
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
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($FichierEnv, [string[]]$lignes, $utf8)
    try {
        New-Item -ItemType Directory -Force -Path (Split-Path $EnvCommun) | Out-Null
        [System.IO.File]::WriteAllLines($EnvCommun, [string[]]$lignes, $utf8)
    } catch { }
}

$Fournisseurs = @(
    @{ Num = '0'; Code = 'ollama'; Nom = 'Ollama sur ce PC (conseillé : gratuit, rien ne sort de la maison)'; Cle = ''
       Site = 'https://ollama.com/download'; Conseil = 'qwen2.5vl:7b' },
    @{ Num = '1'; Code = 'claude'; Nom = 'Claude (Anthropic)'; Cle = 'ANTHROPIC_API_KEY'; Prefixe = 'sk-ant-'
       Site = 'https://console.anthropic.com (API Keys)'; Conseil = 'claude-opus-5' },
    @{ Num = '2'; Code = 'openai'; Nom = 'ChatGPT (OpenAI)'; Cle = 'OPENAI_API_KEY'; Prefixe = 'sk-'
       Site = 'https://platform.openai.com/api-keys'; Conseil = 'gpt-5' },
    @{ Num = '3'; Code = 'gemini'; Nom = 'Gemini (Google)'; Cle = 'GEMINI_API_KEY'; Prefixe = ''
       Site = 'https://aistudio.google.com/apikey'; Conseil = 'gemini-2.5-pro' },
    @{ Num = '4'; Code = 'mistral'; Nom = 'Mistral (français, serveurs en Europe)'; Cle = 'MISTRAL_API_KEY'; Prefixe = ''
       Site = 'https://console.mistral.ai/api-keys'; Conseil = 'mistral-medium-latest' },
    @{ Num = '5'; Code = 'groq'; Nom = 'Groq (très rapide)'; Cle = 'GROQ_API_KEY'; Prefixe = 'gsk_'
       Site = 'https://console.groq.com/keys'; Conseil = 'qwen/qwen3.8-27b' },
    @{ Num = '6'; Code = 'xai'; Nom = 'Grok (xAI)'; Cle = 'XAI_API_KEY'; Prefixe = 'xai-'
       Site = 'https://console.x.ai'; Conseil = 'grok-4' },
    @{ Num = '7'; Code = 'compatible'; Nom = 'Copilot / Azure OpenAI, OpenRouter, Ollama… (compatible OpenAI)'
       Cle = 'LUDIFUN_AI_API_KEY'; Prefixe = ''; Site = 'la console de ton service'; Conseil = '' },
    @{ Num = '8'; Code = 'fake'; Nom = 'IA factice : gratuite, toute photo devient une leçon d''exemple'; Cle = '' }
)

function Nom-IA([string]$code) {
    foreach ($f in $Fournisseurs) { if ($f.Code -eq $code) { return $f.Nom } }
    return $code
}

function Demander-Cle($f, $valeurs) {
    $actuelle = $valeurs[$f.Cle]
    if ($actuelle) {
        $fin = $actuelle.Substring([Math]::Max(0, $actuelle.Length - 4))
        $garder = Read-Host "Une clé $($f.Nom) est déjà enregistrée (…$fin). La garder ? (O/N)"
        if ($garder -notmatch '^[nN]') { return $actuelle }
    }
    while ($true) {
        Write-Host "Colle ta clé d'API $($f.Nom) (clic droit pour coller). Elle se crée sur : $($f.Site)"
        $saisie = (Read-Host 'Clé').Trim()
        if (-not $saisie) {
            if ($f.Code -eq 'compatible') { return '' }  # Ollama : pas de clé
            Write-Host 'Il faut une clé : réessaie.' -ForegroundColor Red
            continue
        }
        if ($f.Prefixe -and -not $saisie.StartsWith($f.Prefixe)) {
            if ($f.Code -eq 'claude') { Write-Host "Une clé Anthropic commence par $($f.Prefixe) : réessaie." -ForegroundColor Red; continue }
            $sur = Read-Host "D'habitude, cette clé commence par $($f.Prefixe). La garder quand même ? (O/N)"
            if ($sur -notmatch '^[oOyY]') { continue }
        }
        return $saisie
    }
}

# Adresse d'Ollama vue depuis Windows : ce PC, ou un autre ordinateur du logement.
function Adresse-Ollama($valeurs) {
    $url = $valeurs['LUDIFUN_OLLAMA_BASE_URL']
    if ($url) { return $url }
    return 'http://localhost:11434'
}

# Ce qui empêche le modèle de bien marcher : il ne lit pas les photos, il est trop gros pour la
# carte graphique (tout passe par le processeur : un quart d'heure par leçon), contexte absent.
function Conseils-Ollama-Injoignable([string]$url) {
    $conseils = @("Ollama ne répond pas à $url")
    $local = $url -match '//(localhost|127\.0\.0\.1|host\.docker\.internal)[:/]'
    $repondIci = $false
    try { Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 3 | Out-Null; $repondIci = $true } catch { }
    if (-not $local -and $repondIci) {
        $conseils += 'Ollama tourne sur ce PC : $(Choix 4), choisis Ollama et garde l''adresse proposée (http://host.docker.internal:11434).'
    } elseif (-not $repondIci -and (Get-Command ollama -ErrorAction SilentlyContinue)) {
        $conseils += 'Ollama est installé mais pas lancé : ouvre Ollama (menu Démarrer), attends l''icône du lama près de l''horloge, puis réessaie.'
    }
    if (-not $local) {
        $conseils += 'Si Ollama est sur un autre PC : sur ce PC-là, setx OLLAMA_HOST 0.0.0.0 puis relancer Ollama, et autoriser le port 11434 dans le pare-feu.'
    }
    return $conseils
}

function Conseils-Ollama([string]$modele, [string]$url, $valeurs) {
    $conseils = @()
    $base = $url.TrimEnd('/')
    try { $tags = Invoke-RestMethod -Uri "$base/api/tags" -TimeoutSec 5 } catch { return (Conseils-Ollama-Injoignable $url) }
    $entree = $tags.models | Where-Object { $_.name -eq $modele -or $_.name -eq "$($modele):latest" } | Select-Object -First 1
    if (-not $entree) { return @("« $modele » n'est pas installé : ollama pull $modele") }
    $go = [math]::Round($entree.size / 1GB, 1)
    if ($go -gt 7) {
        $conseils += "« $modele » pèse $go Go : trop gros pour une carte graphique de 8 Go, il tournera surtout sur le processeur (très lent). Conseillé : qwen2.5vl:7b."
    }
    try {
        $infos = Invoke-RestMethod -Uri "$base/api/show" -Method Post -ContentType 'application/json' -Body (@{ model = $entree.name } | ConvertTo-Json) -TimeoutSec 10
        if ($infos.capabilities -and ($infos.capabilities -notcontains 'vision')) {
            $conseils += "« $modele » ne sait pas lire les images : les photos de leçons échoueront. Conseillé : qwen2.5vl:7b."
        }
    } catch { }
    if (-not $valeurs['LUDIFUN_OLLAMA_NUM_CTX']) {
        $conseils += 'LUDIFUN_OLLAMA_NUM_CTX absent du .env : ajoute LUDIFUN_OLLAMA_NUM_CTX=8192.'
    } elseif ([int]$valeurs['LUDIFUN_OLLAMA_NUM_CTX'] -gt 8192) {
        $conseils += "LUDIFUN_OLLAMA_NUM_CTX=$($valeurs['LUDIFUN_OLLAMA_NUM_CTX']) : avec une carte de 8 Go, 8192 suffit et évite que le modèle déborde de la carte."
    }
    # Ollama sur ce PC : mémoire de travail réduite (PC d'essai, RX 6600 : 9 -> 43 jetons/s). Sans
    # ces réglages, le modèle déborde de la carte graphique dans la mémoire du PC, 4 fois plus lente.
    if (Get-Command ollama -ErrorAction SilentlyContinue) {
        $attendus = [ordered]@{ OLLAMA_FLASH_ATTENTION = '1'; OLLAMA_KV_CACHE_TYPE = 'q8_0'; OLLAMA_NUM_PARALLEL = '1' }
        foreach ($nom in $attendus.Keys) {
            $valeur = [Environment]::GetEnvironmentVariable($nom, 'User')
            if (-not $valeur) { $valeur = [Environment]::GetEnvironmentVariable($nom, 'Machine') }
            if ($valeur -ne $attendus[$nom]) {
                $conseils += "Ollama plus rapide : dans une invite de commandes, setx $nom $($attendus[$nom]) (puis quitter et relancer Ollama)."
            }
        }
        try {
            $charges = (Invoke-RestMethod -Uri "$base/api/ps" -TimeoutSec 5).models
            foreach ($m in $charges) {
                if ($m.size -and $m.size_vram -lt $m.size) {
                    $conseils += "« $($m.name) » ne tient pas entièrement dans la carte graphique ($([math]::Round(100 * $m.size_vram / $m.size)) %) : dans les réglages d'Ollama, mets « Context length » sur 4k."
                }
            }
        } catch { }
    }
    return $conseils
}

function Verifier-Ollama([string]$modele, [string]$url = 'http://localhost:11434') {
    try {
        $tags = Invoke-RestMethod -Uri "$($url.TrimEnd('/'))/api/tags" -TimeoutSec 5
    } catch {
        if ($url -match 'localhost') {
            Write-Host 'Ollama ne répond pas sur ce PC : installe-le (https://ollama.com/download) et lance-le.' -ForegroundColor Yellow
        } else {
            Write-Host "Ollama ne répond pas à $url. Sur l'autre ordinateur : Ollama lancé, variable d'environnement" -ForegroundColor Yellow
            Write-Host 'OLLAMA_HOST=0.0.0.0 (puis redémarrer Ollama), et le pare-feu qui autorise le port 11434.' -ForegroundColor Yellow
        }
        return
    }
    $noms = @($tags.models | ForEach-Object { $_.name })
    if ($noms -contains $modele -or $noms -contains "$($modele):latest") {
        Ok "Ollama répond, « $modele » est installé"
        foreach ($conseil in (Conseils-Ollama $modele $url (Lire-Env))) { Write-Host $conseil -ForegroundColor Yellow }
        return
    }
    Write-Host "Le modèle « $modele » n'est pas encore installé dans Ollama (plusieurs Go à télécharger)." -ForegroundColor Yellow
    if ($url -notmatch 'localhost') {
        Write-Host "Sur l'ordinateur qui a Ollama, dans un terminal : ollama pull $modele"
    } elseif (Get-Command ollama -ErrorAction SilentlyContinue) {
        $oui = Read-Host 'Le télécharger maintenant ? (O/N)'
        if ($oui -match '^[oOyY]') { & ollama pull $modele }
    } else {
        Write-Host "Dans un terminal : ollama pull $modele"
    }
}

function Choisir-IA-Texte {
    $valeurs = Lire-Env
    Write-Host ''
    Write-Host 'Quelle IA doit lire les photos et créer les jeux ?'
    foreach ($f in $Fournisseurs) { Write-Host "  $($f.Num). $($f.Nom)" }
    Write-Host '(Chaque famille peut aussi choisir son IA dans l''application : espace parent → Intelligence artificielle.)'
    $choix = $null
    while (-not $choix) {
        $num = (Read-Host 'Tape le numéro puis Entrée (Entrée seule = 0, Ollama)').Trim()
        if (-not $num) { $num = '0' }
        $choix = $Fournisseurs | Where-Object { $_.Num -eq $num } | Select-Object -First 1
    }
    $valeurs['LUDIFUN_AI_PROVIDER'] = $choix.Code
    if ($choix.Code -eq 'fake') {
        Ecrire-Env $valeurs
        Ok 'IA factice choisie'
        return
    }

    if ($choix.Code -eq 'ollama') {
        # Pas de clé : Ollama répond à qui peut le joindre, sur ce PC ou sur le réseau du logement.
        $valeurs.Remove('LUDIFUN_AI_BASE_URL')  # adresse d'un ancien choix « compatible »
        Write-Host 'Ollama est-il installé sur ce PC ? Entrée = oui.'
        $ou = (Read-Host 'Sinon, adresse IP de l''ordinateur du logement qui l''a (par exemple 192.168.1.20)').Trim()
        if ($ou) {
            if ($ou -notmatch '^https?://') { $ou = "http://$ou" }
            if ($ou -notmatch ':\d+/?$') { $ou = "$($ou.TrimEnd('/')):11434" }
            $valeurs['LUDIFUN_OLLAMA_BASE_URL'] = $ou
        } else {
            $valeurs.Remove('LUDIFUN_OLLAMA_BASE_URL')  # ce PC : host.docker.internal pour le serveur
        }
        $modele = (Read-Host "Modèle Ollama (Entrée = conseillé : $($choix.Conseil))").Trim()
        if ($modele) { $valeurs['LUDIFUN_AI_MODEL'] = $modele } else { $valeurs.Remove('LUDIFUN_AI_MODEL'); $modele = $choix.Conseil }
        Ecrire-Env $valeurs
        Ok 'Ollama choisi (gratuit, sans clé)'
        Verifier-Ollama $modele (Adresse-Ollama $valeurs)
        return
    }

    if ($choix.Code -eq 'compatible') {
        Write-Host 'Adresse de l''API (se termine souvent par /v1). Exemples :'
        Write-Host '  Azure OpenAI (Copilot) : https://<ta-ressource>.openai.azure.com/openai/v1'
        Write-Host '  OpenRouter : https://openrouter.ai/api/v1'
        Write-Host '  Ollama sur ce PC : http://host.docker.internal:11434/v1'
        $url = ''
        while (-not $url) { $url = (Read-Host 'Adresse').Trim() }
        $valeurs['LUDIFUN_AI_BASE_URL'] = $url
    }
    $valeurs[$choix.Cle] = Demander-Cle $choix $valeurs

    if ($choix.Conseil) {
        $modele = (Read-Host "Modèle (Entrée = conseillé : $($choix.Conseil))").Trim()
    } else {
        $modele = ''
        while (-not $modele) { $modele = (Read-Host 'Nom du modèle (il doit savoir lire les images), par exemple gpt-5').Trim() }
    }
    if ($modele) { $valeurs['LUDIFUN_AI_MODEL'] = $modele } else { $valeurs.Remove('LUDIFUN_AI_MODEL') }

    if (-not $valeurs['LUDIFUN_AI_DAILY_BUDGET_USD']) { $valeurs['LUDIFUN_AI_DAILY_BUDGET_USD'] = '5' }
    Ecrire-Env $valeurs
    Ok "$($choix.Nom) choisi (dépense plafonnée à $($valeurs['LUDIFUN_AI_DAILY_BUDGET_USD']) `$ par jour, modifiable dans .env)"
    if ($choix.Code -ne 'claude') {
        Write-Host 'Bon à savoir : Ludifun a été réglé avec Claude ; avec une autre IA, vérifie que les jeux créés sont justes.' -ForegroundColor Yellow
    }
    if ($choix.Code -eq 'gemini') {
        Write-Host 'Gemini gratuit peut réutiliser les données envoyées : pour des leçons d''enfants, active la facturation (offre payante).' -ForegroundColor Yellow
    }
}

# Choix de l'IA en deux temps : celle qui lit les photos (OCR) et crée les jeux, puis celle qui
# dessine les images des leçons (facultatif : sur ce PC, ou en ligne avec Pollinations).
function Choisir-IA {
    Choisir-IA-Texte
    Choisir-Images
}

function Regler-Pollinations($valeurs) {
    Write-Host 'Pollinations dessine en ligne : seule une description écrite par Ludifun part (le sujet de la'
    Write-Host 'notion, jamais de photo ni de prénom). Crée une clé secrète (elle commence par sk_) sur :'
    Write-Host '  https://enter.pollinations.ai/keys'
    $actuelle = $valeurs['LUDIFUN_IMAGE_API_KEY']
    if ($actuelle) {
        $fin = $actuelle.Substring([Math]::Max(0, $actuelle.Length - 4))
        $garder = Read-Host "Une clé Pollinations est déjà enregistrée (…$fin). La garder ? (O/N)"
        if ($garder -match '^[nN]') { $actuelle = '' }
    }
    $cle = $actuelle
    while (-not $cle) {
        $cle = (Read-Host 'Colle la clé (clic droit pour coller)').Trim()
        if ($cle -and -not $cle.StartsWith('sk_')) {
            $sur = Read-Host 'D''habitude, cette clé commence par sk_. La garder quand même ? (O/N)'
            if ($sur -notmatch '^[oOyY]') { $cle = '' }
        }
    }
    $valeurs['LUDIFUN_IMAGE_ENGINE'] = 'pollinations'
    $valeurs['LUDIFUN_IMAGE_API_KEY'] = $cle
    $valeurs.Remove('LUDIFUN_IMAGE_URL')  # adresse du moteur sur ce PC, s'il y en avait un
}

$NomsImages = @{
    'none' = 'pas d''images'; 'sdcpp' = 'sur ce PC'; 'comfyui' = 'ComfyUI sur ce PC'
    'pollinations' = 'en ligne avec Pollinations'
}

function Choisir-Images {
    $valeurs = Lire-Env
    $actuel = $valeurs['LUDIFUN_IMAGE_ENGINE']
    if (-not $actuel) { $actuel = 'none' }
    Write-Host ''
    Write-Host 'Et pour les images des leçons (facultatif), qui les dessine ?'
    Write-Host '  0. Pas d''images'
    Write-Host "  1. Sur ce PC (gratuit, tout reste à la maison ; s'installe une fois avec $(Choix 8))"
    Write-Host '  2. En ligne avec Pollinations (sans carte graphique ; clé à créer sur leur site)'
    $num = (Read-Host "Tape le numéro puis Entrée (Entrée seule = garder : $($NomsImages[$actuel]))").Trim()
    switch ($num) {
        '0' { $valeurs['LUDIFUN_IMAGE_ENGINE'] = 'none' }
        '1' {
            if (-not $valeurs['LUDIFUN_IMAGE_DIR']) {
                Write-Host "Le moteur d'images n'est pas encore installé sur ce PC : lance $(Choix 8), option 1." -ForegroundColor Yellow
                return
            }
            $valeurs['LUDIFUN_IMAGE_ENGINE'] = 'sdcpp'
            $valeurs['LUDIFUN_IMAGE_URL'] = "http://host.docker.internal:$PortImages"
        }
        '2' { Regler-Pollinations $valeurs }
        default { return }
    }
    Ecrire-Env $valeurs
    Ok "Images : $($NomsImages[$valeurs['LUDIFUN_IMAGE_ENGINE']])"
}

function Secret-Aleatoire {
    $octets = New-Object byte[] 48
    $generateur = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $generateur.GetBytes($octets)
    $generateur.Dispose()
    return [Convert]::ToBase64String($octets).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Assurer-Env {
    # Nouveau dossier : les réglages de la copie précédente de Ludifun sont repris.
    if (-not (Test-Path $FichierEnv) -and (Test-Path $EnvCommun)) {
        Copy-Item $EnvCommun $FichierEnv
        Ok 'Réglages repris de la copie précédente de Ludifun (IA, clé, secrets).'
    }
    $valeurs = Lire-Env
    if (-not $valeurs['LUDIFUN_AI_PROVIDER']) { Choisir-IA }
    # Secrets propres à ce PC (connexions des parents, clés d'IA chiffrées) : tirés une fois pour
    # toutes. Les clés d'IA déjà enregistrées sont rechiffrées au démarrage du serveur.
    $valeurs = Lire-Env
    $communs = [ordered]@{}
    if (Test-Path $EnvCommun) {
        foreach ($ligne in Get-Content $EnvCommun -Encoding UTF8) {
            if ($ligne -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') { $communs[$Matches[1]] = $Matches[2].Trim() }
        }
    }
    $ajout = $false
    foreach ($nom in 'LUDIFUN_JWT_SECRET', 'LUDIFUN_SECRETS_KEY') {
        # Les secrets déjà tirés sur ce PC d'abord : un nouveau secret rendrait les clés illisibles.
        if (-not $valeurs[$nom]) { $valeurs[$nom] = if ($communs[$nom]) { $communs[$nom] } else { Secret-Aleatoire }; $ajout = $true }
    }
    if ($ajout) {
        Ecrire-Env $valeurs
        Ok 'Secrets de ce PC créés dans .env (à garder pour soi).'
    }
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
    Echec "Le serveur ne répond pas. Lance $(Choix 9) (voir les erreurs) et envoie le résultat."
}

function Afficher-IA($sante) {
    if ($sante.ai -and $sante.ai -ne 'fake') {
        Ok "IA : $(Nom-IA $sante.ai) (vraie analyse des photos)"
    } else {
        Write-Host "IA : factice (toute photo devient une leçon d'exemple). Pour la vraie IA : $(Choix 4)" -ForegroundColor Yellow
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

# --- Moteur d'images (étape 27, facultatif) ---------------------------------------------

$PortImages = 7860

function Moteur-Images-Repond {
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:$PortImages/sdapi/v1/samplers" -TimeoutSec 3 | Out-Null
        return $true
    } catch { return $false }
}

# Lance sd-server en arrière-plan, sur ce PC seulement (127.0.0.1). Les paramètres du modèle sont
# relus sur le disque à chaque image (« --params-backend disk ») : la carte graphique est rendue
# à Ollama dès l'image finie. Un échec n'empêche pas Ludifun de démarrer : pas d'image, c'est tout.
function Demarrer-Moteur-Images($valeurs) {
    if ($valeurs['LUDIFUN_IMAGE_ENGINE'] -ne 'sdcpp' -or -not $valeurs['LUDIFUN_IMAGE_DIR']) { return }
    if (Moteur-Images-Repond) { Ok 'Moteur d''images déjà lancé'; return }
    $dossier = $valeurs['LUDIFUN_IMAGE_DIR']
    $exe = Get-ChildItem (Join-Path $dossier 'programme') -Recurse -Filter 'sd-server.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
    $modele = Join-Path $dossier 'modeles\sdxl_lightning_4step.safetensors'
    $vae = Join-Path $dossier 'modeles\sdxl_vae.safetensors'
    if (-not $exe -or -not (Test-Path $modele)) {
        Write-Host "Moteur d'images incomplet dans $dossier : relance $(Choix 8)." -ForegroundColor Yellow
        return
    }
    $aide = (& $exe.FullName -h 2>&1 | Out-String)
    $arguments = @('-m', "`"$modele`"", '--listen-ip', '127.0.0.1', '--listen-port', "$PortImages")
    if (Test-Path $vae) { $arguments += @('--vae', "`"$vae`"") }
    if ($aide -match '--params-backend') { $arguments += @('--params-backend', 'disk') }
    elseif ($aide -match '--offload-to-cpu') { $arguments += '--offload-to-cpu' }
    if ($aide -match '--vae-tiling') { $arguments += '--vae-tiling' }
    Etape 'Lancement du moteur d''images…'
    Start-Process -FilePath $exe.FullName -ArgumentList $arguments -WorkingDirectory $exe.DirectoryName -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $dossier 'moteur-images.log') -RedirectStandardError (Join-Path $dossier 'moteur-images-erreurs.log')
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 2
        if (Moteur-Images-Repond) { Ok "Moteur d'images prêt (port $PortImages)"; return }
        if (-not (Get-Process -Name 'sd-server' -ErrorAction SilentlyContinue)) { break }
    }
    Write-Host "Le moteur d'images ne répond pas : voir $(Join-Path $dossier 'moteur-images-erreurs.log'). Ludifun marche sans images." -ForegroundColor Yellow
}

function Arreter-Moteur-Images {
    $processus = Get-Process -Name 'sd-server' -ErrorAction SilentlyContinue
    if ($processus) { $processus | Stop-Process -Force; Ok 'Moteur d''images arrêté' }
}

# --- Recherche sur les sites éducatifs (étapes 24 et 29, facultative) --------------------

$UrlRecherche = 'http://recherche:8080'

function Recherche-Active($valeurs) {
    return [bool]$valeurs['LUDIFUN_WEB_SEARCH_URL'] -and (($valeurs['COMPOSE_PROFILES'] -split ',') -contains 'recherche')
}

# Le moteur SearXNG tourne dans Docker (profil « recherche ») ; Ludifun ne lit que les sites
# autorisés (Vikidia, Lumni, Éduscol…). Chaque parent l'autorise ensuite dans l'application.
function Regler-Recherche($valeurs, [bool]$active) {
    $profils = @(($valeurs['COMPOSE_PROFILES'] -split ',') | Where-Object { $_ -and $_ -ne 'recherche' })
    if ($active) {
        $profils += 'recherche'
        $valeurs['LUDIFUN_WEB_SEARCH_URL'] = $UrlRecherche
    } else {
        $valeurs.Remove('LUDIFUN_WEB_SEARCH_URL')
    }
    if ($profils.Count) { $valeurs['COMPOSE_PROFILES'] = $profils -join ',' } else { $valeurs.Remove('COMPOSE_PROFILES') }
    Ecrire-Env $valeurs
}

function Expliquer-Recherche {
    Write-Host 'Dans l''application : espace parent → Mon compte → Intelligence artificielle →'
    Write-Host '« 📚 Utiliser des sites éducatifs de confiance » (chaque famille décide pour elle).'
}

# --- Sauvegardes de la base -------------------------------------------------------------

# Hors du dossier de Ludifun, à côté des réglages : un nouveau dossier (ZIP téléchargé à nouveau)
# les retrouve. Une sauvegarde contient les comptes, les leçons et les résultats des enfants :
# elle reste sur ce PC (à copier sur une clé USB avec reglages.env pour changer de PC).
$DossierSauvegardes = Join-Path $env:LOCALAPPDATA 'Ludifun\sauvegardes'
$SauvegardesGardees = 14
$MarqueSchema = Join-Path $env:LOCALAPPDATA 'Ludifun\schema.txt'

function Base-Existe {
    & docker volume inspect ludifun_pgdata *> $null
    return $LASTEXITCODE -eq 0
}

function Assurer-Base {
    & docker compose up -d db *> $null
    if ($LASTEXITCODE -ne 0) { return $false }
    for ($i = 0; $i -lt 30; $i++) {
        & docker compose exec -T db pg_isready -U ludifun -d ludifun *> $null
        if ($LASTEXITCODE -eq 0) { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

# Les fonctions qui renvoient un résultat envoient l'affichage des commandes à l'écran
# (`| Out-Host`) : sinon il se mêlerait au résultat.

# Dernière migration de ce dossier : quand elle change (nouvelle version), le serveur va
# transformer la base au démarrage ; on la sauvegarde avant.
function Schema-Du-Dossier {
    $dernier = Get-ChildItem (Join-Path $Racine 'backend\migrations\versions') -Filter '*.py' |
        Sort-Object Name | Select-Object -Last 1
    if ($dernier) { return $dernier.BaseName } else { return '' }
}

function Sauvegarder-Base([string]$raison = 'manuelle') {
    if (-not (Assurer-Base)) { return $null }
    New-Item -ItemType Directory -Force -Path $DossierSauvegardes | Out-Null
    $chemin = Join-Path $DossierSauvegardes "ludifun-$(Get-Date -Format 'yyyy-MM-dd-HHmmss')-$raison.dump"
    # pg_dump écrit dans le conteneur, puis le fichier est copié tel quel (jamais par un tube
    # PowerShell, qui abîmerait un fichier binaire). Copie vers un nom relatif : « C: » ne
    # risque pas d'être pris pour un nom de conteneur.
    & docker compose exec -T db pg_dump -U ludifun -d ludifun --format=custom --file=/tmp/sauvegarde.dump | Out-Host
    if ($LASTEXITCODE -ne 0) { return $null }
    $temporaire = 'sauvegarde-en-cours.tmp'
    & docker compose cp db:/tmp/sauvegarde.dump $temporaire | Out-Host
    $copie = $LASTEXITCODE
    & docker compose exec -T db rm -f /tmp/sauvegarde.dump *> $null
    if ($copie -ne 0 -or -not (Test-Path $temporaire) -or (Get-Item $temporaire).Length -eq 0) {
        Remove-Item $temporaire -Force -ErrorAction SilentlyContinue
        return $null
    }
    Move-Item $temporaire $chemin -Force
    Get-ChildItem $DossierSauvegardes -Filter 'ludifun-*.dump' | Sort-Object LastWriteTime -Descending |
        Select-Object -Skip $SauvegardesGardees | Remove-Item -Force -ErrorAction SilentlyContinue
    return $chemin
}

# Au démarrage : une sauvegarde avant qu'une nouvelle version transforme la base, et sinon une
# par jour. Une panne ici n'empêche jamais Ludifun de démarrer.
function Sauvegarde-Automatique {
    if (-not (Base-Existe)) { return }
    $schema = Schema-Du-Dossier
    $connu = if (Test-Path $MarqueSchema) { (Get-Content $MarqueSchema -Raw).Trim() } else { '' }
    $derniere = Get-ChildItem $DossierSauvegardes -Filter 'ludifun-*.dump' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $raison = if ($schema -ne $connu) { 'avant-mise-a-jour' }
        elseif (-not $derniere -or $derniere.LastWriteTime -lt (Get-Date).AddHours(-20)) { 'quotidienne' }
        else { '' }
    if (-not $raison) { return }
    Etape 'Sauvegarde des données des enfants…'
    $fichier = Sauvegarder-Base $raison
    if ($fichier) {
        Ok "Sauvegarde faite : $fichier"
        New-Item -ItemType Directory -Force -Path (Split-Path $MarqueSchema) | Out-Null
        Set-Content -Path $MarqueSchema -Value $schema
    } else {
        Write-Host 'La sauvegarde n''a pas pu être faite (Ludifun démarre quand même).' -ForegroundColor Yellow
    }
}

# Remet une sauvegarde : elle est d'abord chargée dans une base à part ; la base actuelle n'est
# remplacée que si tout s'est bien passé. Le serveur, redémarré ensuite, met la base à jour si
# la sauvegarde vient d'une version plus ancienne.
function Restaurer-Base([string]$chemin) {
    if (-not (Assurer-Base)) { return 'La base ne démarre pas.' }
    Copy-Item $chemin 'restauration.tmp' -Force
    & docker compose cp 'restauration.tmp' db:/tmp/restauration.dump | Out-Host
    $copie = $LASTEXITCODE
    Remove-Item 'restauration.tmp' -Force -ErrorAction SilentlyContinue
    if ($copie -ne 0) { return 'La sauvegarde n''a pas pu être copiée.' }
    & docker compose stop api *> $null
    & docker compose exec -T db sh -c 'dropdb -U ludifun --if-exists ludifun_restauration && createdb -U ludifun -O ludifun ludifun_restauration && pg_restore -U ludifun -d ludifun_restauration --no-owner --exit-on-error /tmp/restauration.dump' | Out-Host
    if ($LASTEXITCODE -ne 0) {
        & docker compose exec -T db sh -c 'dropdb -U ludifun --if-exists ludifun_restauration; rm -f /tmp/restauration.dump' *> $null
        return 'La sauvegarde est illisible : rien n''a été changé.'
    }
    & docker compose exec -T db sh -c 'rm -f /tmp/restauration.dump' *> $null
    & docker compose exec -T db psql -U ludifun -d postgres -v ON_ERROR_STOP=1 `
        -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'ludifun' AND pid <> pg_backend_pid();" `
        -c 'DROP DATABASE IF EXISTS ludifun_avant_restauration;' `
        -c 'ALTER DATABASE ludifun RENAME TO ludifun_avant_restauration;' `
        -c 'ALTER DATABASE ludifun_restauration RENAME TO ludifun;' | Out-Host
    if ($LASTEXITCODE -ne 0) {
        # La base actuelle reprend son nom si elle l'avait perdu.
        & docker compose exec -T db psql -U ludifun -d postgres -c 'ALTER DATABASE ludifun_avant_restauration RENAME TO ludifun;' *> $null
        return 'Le remplacement de la base n''a pas fonctionné : rien n''a été changé.'
    }
    & docker compose exec -T db dropdb -U ludifun --if-exists ludifun_avant_restauration *> $null
    return ''
}

# --- Mises à jour (GitHub) --------------------------------------------------------------

# Le code et l'application du téléphone sont sur GitHub. Le dépôt étant privé, la mise à jour a
# besoin d'une clé de lecture (« jeton »), demandée une fois. Elle est chiffrée pour la session
# Windows (DPAPI) et rangée avec les réglages, hors du dossier de Ludifun : jamais dans le dépôt,
# jamais envoyée ailleurs qu'à GitHub.
$DepotGitHub = if ($env:LUDIFUN_DEPOT) { $env:LUDIFUN_DEPOT } else { 'Ricoudc/Ludifun' }
$ApiGitHub = if ($env:LUDIFUN_API_GITHUB) { $env:LUDIFUN_API_GITHUB } else { 'https://api.github.com' }  # autre adresse : tests
$FichierJeton = Join-Path $env:LOCALAPPDATA 'Ludifun\jeton-github.txt'
$MarqueVersion = Join-Path $Racine '.ludifun-version'
$ListeFichiers = Join-Path $Racine '.ludifun-fichiers'
$DossierTelephone = Join-Path $Racine 'telephone'
$MarqueApk = Join-Path $DossierTelephone 'version.txt'

function Installe-Avec-Git {
    return [bool]((Get-Command git -ErrorAction SilentlyContinue) -and (Test-Path (Join-Path $Racine '.git')))
}

function Jeton-GitHub {
    if (-not (Test-Path $FichierJeton)) { return $null }
    try {
        $secret = Get-Content $FichierJeton -Raw | ConvertTo-SecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
        try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    } catch { return $null }  # autre session Windows, fichier abîmé : on le redemandera
}

function Client-Http([bool]$suivre) {
    Add-Type -AssemblyName System.Net.Http
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $gestion = New-Object System.Net.Http.HttpClientHandler
    $gestion.AllowAutoRedirect = $suivre
    $client = New-Object System.Net.Http.HttpClient($gestion)
    $client.Timeout = [TimeSpan]::FromMinutes(15)
    $client.DefaultRequestHeaders.UserAgent.ParseAdd('Ludifun-mise-a-jour')
    return $client
}

# Appel à l'API de GitHub. Une redirection (archive, fichier d'une version) est suivie SANS le
# jeton : il ne part que vers l'API. Renvoie la réponse (à lire puis libérer).
function Requete-GitHub([string]$url, [string]$accept, $jeton, [int]$delai = 0) {
    $client = Client-Http $false
    if ($delai -gt 0) { $client.Timeout = [TimeSpan]::FromSeconds($delai) }
    $demande = New-Object System.Net.Http.HttpRequestMessage([System.Net.Http.HttpMethod]::Get, $url)
    $demande.Headers.Accept.ParseAdd($accept)
    $demande.Headers.Add('X-GitHub-Api-Version', '2022-11-28')
    if ($jeton) { $demande.Headers.Authorization = New-Object System.Net.Http.Headers.AuthenticationHeaderValue('Bearer', $jeton) }
    $reponse = $client.SendAsync($demande, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
    $code = [int]$reponse.StatusCode
    if ($code -ge 300 -and $code -lt 400 -and $reponse.Headers.Location) {
        $suite = Client-Http $true
        return $suite.GetAsync($reponse.Headers.Location, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
    }
    return $reponse
}

# Objet JSON de l'API ; $null si GitHub refuse (dépôt privé sans jeton valable) ; une exception
# si GitHub est injoignable.
function Api-GitHub([string]$chemin, $jeton, [int]$delai = 0) {
    $reponse = Requete-GitHub "$ApiGitHub/repos/$DepotGitHub$chemin" 'application/vnd.github+json' $jeton $delai
    $code = [int]$reponse.StatusCode
    if ($code -in 401, 403, 404) { return $null }
    if (-not $reponse.IsSuccessStatusCode) { throw "GitHub a répondu $code" }
    return $reponse.Content.ReadAsStringAsync().GetAwaiter().GetResult() | ConvertFrom-Json
}

function Telecharger-GitHub([string]$url, [string]$accept, $jeton, [string]$sortie) {
    $reponse = Requete-GitHub $url $accept $jeton
    if (-not $reponse.IsSuccessStatusCode) { throw "téléchargement refusé ($([int]$reponse.StatusCode))" }
    $flux = $reponse.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
    $fichier = [IO.File]::Create($sortie)
    try { $flux.CopyTo($fichier) } finally { $fichier.Close(); $flux.Close() }
}

function Demander-Jeton {
    Write-Host ''
    Write-Host 'Le code de Ludifun est privé sur GitHub : il faut une clé de lecture, une seule fois.' -ForegroundColor Cyan
    Write-Host 'La page de GitHub va s''ouvrir (connecte-toi si besoin), puis :'
    Write-Host '  1. Token name : Ludifun PC ; Expiration : 1 an (ou plus) ;'
    Write-Host '  2. Repository access : « Only select repositories » → Ludifun ;'
    Write-Host '  3. Permissions → Repository permissions → Contents : « Read-only » ;'
    Write-Host '  4. « Generate token », copie le jeton (github_pat_…) et colle-le ici.'
    Write-Host 'Il reste chiffré sur ce PC, pour ta session Windows ; il ne permet que de lire Ludifun.'
    Start-Process 'https://github.com/settings/personal-access-tokens/new'
    for ($essai = 0; $essai -lt 3; $essai++) {
        $secret = Read-Host 'Jeton GitHub (il ne s''affiche pas ; Entrée seule pour abandonner)' -AsSecureString
        if ($secret.Length -eq 0) { return $null }
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
        try { $jeton = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr).Trim() }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
        if (Api-GitHub '' $jeton) {
            New-Item -ItemType Directory -Force -Path (Split-Path $FichierJeton) | Out-Null
            ConvertTo-SecureString $jeton -AsPlainText -Force | ConvertFrom-SecureString | Set-Content $FichierJeton
            Ok 'Jeton enregistré : les prochaines mises à jour seront automatiques.'
            return $jeton
        }
        Write-Host 'GitHub refuse ce jeton (mal copié, ou sans accès à Ludifun en lecture). Réessaie.' -ForegroundColor Yellow
    }
    return $null
}

# Le jeton s'il en faut un : aucun si le dépôt est public, celui enregistré, sinon demandé.
# $false : pas d'accès (abandon) ; une exception : GitHub injoignable.
function Acces-GitHub([bool]$demander = $true) {
    if (Api-GitHub '' $null) { return '' }
    $jeton = Jeton-GitHub
    if ($jeton -and (Api-GitHub '' $jeton)) { return $jeton }
    if ($jeton) { Write-Host 'Le jeton GitHub enregistré ne marche plus (expiré ?) : il en faut un nouveau.' -ForegroundColor Yellow }
    if (-not $demander) { return $false }
    $nouveau = Demander-Jeton
    if ($nouveau) { return $nouveau } else { return $false }
}

function Version-Installee {
    if (Installe-Avec-Git) { return (& git -C $Racine rev-parse HEAD 2>$null) }
    if (Test-Path $MarqueVersion) { return (Get-Content $MarqueVersion -Raw).Trim() }
    return ''
}

# Dernière version publiée (branche principale) : son identifiant et sa date.
function Derniere-Version($jeton, [int]$delai = 0) {
    $commits = Api-GitHub '/commits?per_page=1' $jeton $delai
    if (-not $commits) { return $null }
    $dernier = @($commits)[0]
    return [pscustomobject]@{ Sha = $dernier.sha; Date = $dernier.commit.committer.date }
}

# Pour le menu : vrai si une version plus récente attend (vérifié vite, sans rien demander).
function Mise-A-Jour-Disponible {
    try {
        $jeton = if (Api-GitHub '' $null 4) { '' } else { Jeton-GitHub }
        if ($null -eq $jeton) { return $false }
        $derniere = Derniere-Version $jeton 4
        return [bool]($derniere -and $derniere.Sha -ne (Version-Installee))
    } catch { return $false }
}
