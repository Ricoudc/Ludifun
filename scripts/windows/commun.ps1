# Fonctions partagées par les scripts Windows de Ludifun (démarrer, arrêter, mettre à jour…).
# Rien ici n'envoie de donnée ailleurs que sur ce PC : le fichier .env reste local.

$ErrorActionPreference = 'Continue'
$Racine = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$FichierEnv = Join-Path $Racine '.env'
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
    [System.IO.File]::WriteAllLines($FichierEnv, [string[]]$lignes, (New-Object System.Text.UTF8Encoding($false)))
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
function Conseils-Ollama([string]$modele, [string]$url, $valeurs) {
    $conseils = @()
    $base = $url.TrimEnd('/')
    try { $tags = Invoke-RestMethod -Uri "$base/api/tags" -TimeoutSec 5 } catch { return @("Ollama ne répond pas à $url") }
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
        $conseils += 'LUDIFUN_OLLAMA_NUM_CTX absent du .env : avec une carte de 8 Go, ajoute LUDIFUN_OLLAMA_NUM_CTX=8192.'
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

function Choisir-IA {
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

function Secret-Aleatoire {
    $octets = New-Object byte[] 48
    $generateur = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $generateur.GetBytes($octets)
    $generateur.Dispose()
    return [Convert]::ToBase64String($octets).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Assurer-Env {
    $valeurs = Lire-Env
    if (-not $valeurs['LUDIFUN_AI_PROVIDER']) { Choisir-IA }
    # Secrets propres à ce PC (connexions des parents, clés d'IA chiffrées) : tirés une fois pour
    # toutes. Les clés d'IA déjà enregistrées sont rechiffrées au démarrage du serveur.
    $valeurs = Lire-Env
    $ajout = $false
    foreach ($nom in 'LUDIFUN_JWT_SECRET', 'LUDIFUN_SECRETS_KEY') {
        if (-not $valeurs[$nom]) { $valeurs[$nom] = Secret-Aleatoire; $ajout = $true }
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
    Echec 'Le serveur ne répond pas. Double-clique sur Voir-les-erreurs-Ludifun.bat et envoie le résultat.'
}

function Afficher-IA($sante) {
    if ($sante.ai -and $sante.ai -ne 'fake') {
        Ok "IA : $(Nom-IA $sante.ai) (vraie analyse des photos)"
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
