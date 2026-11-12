# Vérifie tout Ludifun sur ce PC, comme le fait GitHub à chaque envoi de code : serveur (style,
# types, tests), application du téléphone (format, analyse, tests) et scripts Windows (syntaxe,
# UTF-8 avec BOM, fins de ligne CRLF). Chaque partie est lancée même si une autre échoue ; un
# résumé dit ce qui va et ce qui ne va pas.
#
#   scripts\windows\verifier.ps1                 tout
#   scripts\windows\verifier.ps1 -Serveur        le serveur seulement
#   scripts\windows\verifier.ps1 -Application    l'application seulement
#   scripts\windows\verifier.ps1 -Scripts        les scripts Windows seulement
#
# Outils : Docker Desktop et uv (serveur), Flutter (application). Les tests du serveur utilisent
# la base « ludifun_test » du PostgreSQL de Ludifun, jamais celle de la famille.
param([switch]$Serveur, [switch]$Application, [switch]$Scripts, [switch]$SansPause)

. (Join-Path $PSScriptRoot 'commun.ps1')

$tout = -not ($Serveur -or $Application -or $Scripts)
$resultats = [System.Collections.Generic.List[object]]::new()

function Noter([string]$partie, [string]$etape, [bool]$reussi, [string]$detail = '') {
    $resultats.Add([pscustomobject]@{ Partie = $partie; Etape = $etape; Reussi = $reussi; Detail = $detail })
    if ($reussi) { Ok "$partie : $etape" } else { Write-Host "ECHEC  $partie : $etape $detail" -ForegroundColor Red }
}

# Lance une commande dans un dossier ; réussie si son code de sortie est 0.
function Lancer([string]$partie, [string]$etape, [string]$dossier, [scriptblock]$commande) {
    Etape "$partie : $etape"
    Push-Location $dossier
    try {
        & $commande
        Noter $partie $etape ($LASTEXITCODE -eq 0)
    } catch {
        Noter $partie $etape $false $_.Exception.Message
    } finally {
        Pop-Location
    }
}

function Outil([string]$nom) { return [bool](Get-Command $nom -ErrorAction SilentlyContinue) }

# --- Serveur --------------------------------------------------------------------------------

if ($tout -or $Serveur) {
    Titre 'Serveur'
    $backend = Join-Path $Racine 'backend'
    if (-not (Outil 'uv')) {
        Noter 'Serveur' 'uv installé' $false '(PowerShell : irm https://astral.sh/uv/install.ps1 | iex, puis rouvrir la fenêtre)'
    } elseif (-not (Outil 'docker')) {
        Noter 'Serveur' 'Docker installé' $false '(https://www.docker.com/products/docker-desktop)'
    } else {
        Assurer-Docker
        Etape 'Serveur : base de données de test'
        & docker compose up -d --wait db
        if ($LASTEXITCODE -ne 0) {
            Noter 'Serveur' 'PostgreSQL démarré' $false '(voir les messages de Docker au-dessus)'
        } else {
            # Base dédiée aux tests, au port des scripts Windows : les données de la famille ne
            # sont jamais touchées.
            $env:LUDIFUN_TEST_DATABASE_URL = "postgresql+asyncpg://ludifun:ludifun@localhost:$($env:LUDIFUN_DB_PORT)/ludifun_test"
            Lancer 'Serveur' 'dépendances (uv sync)' $backend { & uv sync --frozen }
            Lancer 'Serveur' 'style (ruff check)' $backend { & uv run ruff check . }
            Lancer 'Serveur' 'mise en forme (ruff format)' $backend { & uv run ruff format --check . }
            Lancer 'Serveur' 'types (mypy)' $backend { & uv run mypy app tests }
            Lancer 'Serveur' 'tests (pytest)' $backend { & uv run pytest -q }
        }
    }
}

# --- Application du téléphone ---------------------------------------------------------------

if ($tout -or $Application) {
    Titre 'Application du téléphone'
    $mobile = Join-Path $Racine 'mobile'
    if (-not (Outil 'flutter')) {
        Noter 'Application' 'Flutter installé' $false '(https://docs.flutter.dev/get-started/install/windows)'
    } else {
        Lancer 'Application' 'dépendances (flutter pub get)' $mobile { & flutter pub get --enforce-lockfile }
        # Vérifie sans modifier : « dart format lib test » corrige la mise en forme.
        Lancer 'Application' 'mise en forme (dart format)' $mobile { & dart format --output=none --set-exit-if-changed lib test }
        Lancer 'Application' 'analyse (flutter analyze)' $mobile { & flutter analyze }
        Lancer 'Application' 'tests (flutter test)' $mobile { & flutter test }
    }
}

# --- Scripts Windows ------------------------------------------------------------------------

if ($tout -or $Scripts) {
    Titre 'Scripts Windows'
    $fichiers = @(Get-ChildItem (Join-Path $Racine 'scripts\windows') -Filter '*.ps1')
    $mauvais = @()
    foreach ($fichier in $fichiers) {
        $octets = [System.IO.File]::ReadAllBytes($fichier.FullName)
        $texte = [System.Text.Encoding]::UTF8.GetString($octets)
        $erreurs = $null
        [void][System.Management.Automation.Language.Parser]::ParseFile($fichier.FullName, [ref]$null, [ref]$erreurs)
        $raisons = @()
        if ($erreurs) { $raisons += "syntaxe ligne $($erreurs[0].Extent.StartLineNumber) : $($erreurs[0].Message)" }
        if ($octets.Length -lt 3 -or $octets[0] -ne 0xEF -or $octets[1] -ne 0xBB -or $octets[2] -ne 0xBF) {
            $raisons += 'pas en UTF-8 avec BOM'
        }
        if ($texte -match "(?<!`r)`n") { $raisons += 'fins de ligne LF au lieu de CRLF' }
        if ($raisons) { $mauvais += "$($fichier.Name) : $($raisons -join ', ')" }
    }
    foreach ($ligne in $mauvais) { Write-Host "  $ligne" -ForegroundColor Red }
    Noter 'Scripts' "$($fichiers.Count) scripts (syntaxe, BOM, CRLF)" ($mauvais.Count -eq 0)
}

# --- Résumé ---------------------------------------------------------------------------------

Titre 'Résumé'
foreach ($r in $resultats) {
    $etat = if ($r.Reussi) { 'OK    ' } else { 'ECHEC ' }
    $couleur = if ($r.Reussi) { 'Green' } else { 'Red' }
    Write-Host ("{0}{1} : {2} {3}" -f $etat, $r.Partie, $r.Etape, $r.Detail) -ForegroundColor $couleur
}
$echecs = @($resultats | Where-Object { -not $_.Reussi }).Count
Write-Host ''
if ($echecs -eq 0) {
    Ok 'Tout est vert : le code peut être envoyé.'
} else {
    Write-Host "$echecs vérification(s) en échec : voir les messages au-dessus de ce résumé." -ForegroundColor Red
}
if (-not $SansPause) {
    Write-Host ''
    if ($DepuisMenu) { Read-Host 'Appuie sur Entrée pour revenir au menu' } else { Read-Host 'Appuie sur Entrée pour fermer' }
}
exit ([int]($echecs -gt 0))
