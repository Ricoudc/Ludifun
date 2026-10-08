# Surveillance pendant un essai : tout ce que fait le serveur (appels à l'IA, durées, erreurs,
# redémarrages), la charge du processeur et de la carte graphique, et ce qu'Ollama garde en
# mémoire, enregistré au fil de l'eau dans surveillance-ludifun.txt. À la fin, le fichier est
# copié : à coller dans la conversation avec Claude. Ni prénom, ni texte de leçon, ni clé d'API.
. (Join-Path $PSScriptRoot 'commun.ps1')

Titre 'Surveillance de Ludifun'
if (-not (Docker-Pret)) { Echec 'Docker n''est pas lancé : lance d''abord Demarrer-Ludifun.bat.' }

# Docker écrit en UTF-8 : sans ce réglage, les accents du journal deviennent illisibles.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$fichier = Join-Path $Racine 'surveillance-ludifun.txt'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($fichier, '', $utf8)

function Noter([string]$texte, [string]$couleur = 'Gray') {
    $ligne = "$(Get-Date -Format 'HH:mm:ss') $texte"
    [System.IO.File]::AppendAllText($fichier, "$ligne`r`n", $utf8)
    Write-Host $ligne -ForegroundColor $couleur
}

# Les programmes qui occupent la mémoire de la carte graphique : si elle est déjà prise avant
# qu'Ollama charge son modèle, le modèle déborde dans la mémoire du PC (6 jetons/s au lieu de 40).
function Occupants-Carte {
    try {
        $compteurs = Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUProcessMemory -ErrorAction Stop
    } catch { return 'non disponible' }
    $parProgramme = $compteurs | Where-Object { $_.Name -match '^pid_(\d+)_' } |
        Group-Object { [int]($_.Name -replace '^pid_(\d+)_.*$', '$1') } |
        ForEach-Object {
            $id = [int]$_.Name
            $nom = (Get-Process -Id $id -ErrorAction SilentlyContinue).ProcessName
            if (-not $nom) { $nom = "processus $id" }
            [pscustomobject]@{ Nom = $nom; Octets = ($_.Group | Measure-Object DedicatedUsage -Sum).Sum }
        } |
        Group-Object Nom | ForEach-Object { [pscustomobject]@{ Nom = $_.Name; Octets = ($_.Group | Measure-Object Octets -Sum).Sum } } |
        Where-Object { $_.Octets -ge 100MB } | Sort-Object Octets -Descending | Select-Object -First 8
    if (-not $parProgramme) { return 'aucun programme au-dessus de 100 Mo' }
    return ($parProgramme | ForEach-Object { "$($_.Nom) $([math]::Round($_.Octets / 1GB, 1)) Go" }) -join ' · '
}

$reglages = Lire-Env
$ollama = (Adresse-Ollama $reglages).TrimEnd('/')
Noter "Surveillance du $(Get-Date -Format 'yyyy-MM-dd')"
foreach ($cle in 'LUDIFUN_AI_PROVIDER', 'LUDIFUN_AI_MODEL', 'LUDIFUN_OLLAMA_BASE_URL', 'LUDIFUN_OLLAMA_NUM_CTX', 'COMPOSE_PROFILES') {
    if ($reglages[$cle]) { Noter "Réglage $cle=$($reglages[$cle])" }
}
try {
    foreach ($carte in Get-CimInstance Win32_VideoController) { Noter "Carte graphique : $($carte.Name) (pilote $($carte.DriverVersion))" }
} catch { }
try { Noter "Ollama $((Invoke-RestMethod -Uri "$ollama/api/version" -TimeoutSec 5).version) à $ollama" } catch { Noter "Ollama ne répond pas à $ollama" 'Red' }

Noter "Carte graphique occupée par : $(Occupants-Carte)"

Write-Host ''
Write-Host 'Fais ton essai sur le téléphone maintenant (photo de la leçon, séance…).' -ForegroundColor Green
Write-Host 'Tout est noté ici au fur et à mesure. Quand c''est fini, appuie sur Entrée.' -ForegroundColor Green
Write-Host ''

# Journal du serveur : tout sauf les requêtes réussies de l'application (trop nombreuses).
$requeteReussie = '"(GET|POST|PUT|PATCH|DELETE) [^"]*" [23]\d\d'
# Chaque ligne porte l'heure de Docker : on reprend après la dernière vue, sans doublon.
$script:derniereVue = (Get-Date).ToUniversalTime().AddMinutes(-2).ToString('yyyy-MM-ddTHH:mm:ssZ')
function Lire-Journal {
    $sortie = & docker compose logs api --since $script:derniereVue --timestamps --no-log-prefix 2>&1
    foreach ($l in $sortie) {
        $brut = "$l".TrimEnd()
        if ($brut -notmatch '^(\d{4}-\d\d-\d\dT\S+Z) ?(.*)$') { continue }
        $heure, $texte = $Matches[1], $Matches[2]
        if ([string]::CompareOrdinal($heure, $script:derniereVue) -le 0) { continue }
        $script:derniereVue = $heure
        if (-not $texte -or $texte -match $requeteReussie) { continue }
        $couleur = if ($texte -match 'ERROR|Traceback|échec|Exception') { 'Red' } elseif ($texte -match 'WARNING|boucle|tronqu') { 'Yellow' } elseif ($texte -match 'IA :|Ollama :') { 'Cyan' } else { 'Gray' }
        Noter "serveur | $texte" $couleur
    }
}

# Charge de la machine : noms de compteurs indépendants de la langue de Windows.
function Charge {
    $morceaux = @()
    try {
        $cpu = (Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'").PercentProcessorTime
        $morceaux += "processeur $cpu %"
    } catch { }
    try {
        $moteurs = Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine -ErrorAction Stop
        $parType = $moteurs | Group-Object { if ($_.Name -match 'engtype_(\w+)') { $Matches[1] } else { '?' } } |
            ForEach-Object { [pscustomobject]@{ Type = $_.Name; Total = ($_.Group | Measure-Object UtilizationPercentage -Sum).Sum } } |
            Where-Object { $_.Total -gt 0 } | Sort-Object Total -Descending | Select-Object -First 3
        $gpu = ($parType | ForEach-Object { "$($_.Type) $([math]::Min(100, $_.Total)) %" }) -join ', '
        if (-not $gpu) { $gpu = 'au repos' }
        $morceaux += "carte graphique $gpu"
        $compteurs = Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory -ErrorAction Stop
        $memoire = ($compteurs | Measure-Object DedicatedUsage -Sum).Sum
        $partagee = ($compteurs | Measure-Object SharedUsage -Sum).Sum
        $morceaux += "mémoire graphique $([math]::Round($memoire / 1GB, 1)) Go"
        # Mémoire partagée qui monte pendant un calcul : la carte déborde dans la mémoire du PC
        # (Ollama affiche quand même « 100 % GPU », mais écrit 2 jetons/s au lieu de 40).
        $morceaux += "partagée $([math]::Round($partagee / 1GB, 1)) Go"
    } catch { }
    try {
        $os = Get-CimInstance Win32_OperatingSystem
        $morceaux += "mémoire libre $([math]::Round($os.FreePhysicalMemory / 1MB, 1)) Go"
    } catch { }
    return $morceaux -join ' · '
}

function Etat-Ollama {
    try {
        $charges = (Invoke-RestMethod -Uri "$ollama/api/ps" -TimeoutSec 5).models
        if (-not $charges) { return 'aucun modèle chargé' }
        return ($charges | ForEach-Object {
            $gpu = if ($_.size) { [math]::Round(100 * $_.size_vram / $_.size) } else { 0 }
            "$($_.name) chargé ($([math]::Round($_.size / 1GB, 1)) Go, $gpu % sur la carte graphique)"
        }) -join ' ; '
    } catch { return "ne répond pas ($($_.Exception.Message))" }
}

$dernierEtat = ''
$derniereOllama = ''
$tour = 0
$touche = $null
while ($true) {
    Lire-Journal

    $etat = (& docker compose ps -a --format '{{.Service}} {{.State}} {{.Status}}' 2>&1) -join ' | '
    $etatCourt = $etat -replace '\d+ (seconds?|minutes?|hours?)', '' -replace 'About an? \w+', ''
    if ($etatCourt -ne $dernierEtat) { Noter "docker | $etat" 'Magenta'; $dernierEtat = $etatCourt }

    $etatOllama = Etat-Ollama
    if ($etatOllama -ne $derniereOllama) { Noter "ollama | $etatOllama" 'Magenta'; $derniereOllama = $etatOllama }

    # La charge toutes les 15 secondes : assez pour voir si la carte graphique travaille.
    if ($tour % 3 -eq 0) { Noter "charge | $(Charge)" 'DarkGray' }
    $tour++

    for ($i = 0; $i -lt 10; $i++) {
        Start-Sleep -Milliseconds 500
        if ([Console]::KeyAvailable) {
            $touche = [Console]::ReadKey($true)
            if ($touche.Key -eq 'Enter') { break }
        }
    }
    if ($touche -and $touche.Key -eq 'Enter') { break }
}

Lire-Journal
Noter "Carte graphique occupée par : $(Occupants-Carte)"
Noter 'Fin de la surveillance'
try {
    $reponse = Invoke-WebRequest -Uri 'http://localhost:8000/suivi/rapport.txt' -UseBasicParsing -TimeoutSec 15
    [System.IO.File]::AppendAllText($fichier, "`r`n##### Appels à l'IA (page /suivi)`r`n" + [System.Text.Encoding]::UTF8.GetString($reponse.RawContentStream.ToArray()) + "`r`n", $utf8)
} catch { }

try { Set-Clipboard -Value ([System.IO.File]::ReadAllText($fichier, $utf8)) } catch { }
Ok "Surveillance enregistrée : $fichier"
Write-Host 'Elle est aussi copiée : colle-la (Ctrl+V) dans la conversation avec Claude, ou envoie le fichier.' -ForegroundColor Green
try { Start-Process notepad.exe $fichier } catch { }
Read-Host 'Appuie sur Entrée pour fermer cette fenêtre (le serveur continue de tourner)'
