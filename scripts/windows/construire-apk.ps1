# Construit l'application du téléphone (APK de test) sur ce PC, comme le fait GitHub, et la range
# dans le dossier « telephone » de Ludifun avec sa fiche (numéro de construction) : le serveur
# la propose alors au téléphone (« Nouvelle version de Ludifun »), sinon copie
# telephone\ludifun.apk sur le téléphone et ouvre-le.
#
#   scripts\windows\construire-apk.ps1               construit et range l'APK
#   scripts\windows\construire-apk.ps1 -SansRanger   construit seulement (mobile\build\…)
#
# Outils : Flutter et Android Studio (le SDK Android) ; « flutter doctor » dit ce qui manque.
# La construction prend plusieurs minutes la première fois.
param([switch]$SansRanger, [switch]$SansPause)

. (Join-Path $PSScriptRoot 'commun.ps1')

function Fin([int]$code) {
    if (-not $SansPause) {
        Write-Host ''
        if ($DepuisMenu) { Read-Host 'Appuie sur Entrée pour revenir au menu' } else { Read-Host 'Appuie sur Entrée pour fermer' }
    }
    exit $code
}

Titre 'Application du téléphone (APK de test)'
if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) {
    Write-Host 'Flutter n''est pas installé : https://docs.flutter.dev/get-started/install/windows' -ForegroundColor Red
    Write-Host 'Installe aussi Android Studio, puis lance « flutter doctor --android-licenses ».'
    Fin 1
}

# Numéro de construction : plus grand que celui de l'APK déjà rangé (celui de GitHub ou une
# construction précédente), pour que le téléphone propose la mise à jour.
$fiche = Join-Path $DossierTelephone 'ludifun.json'
$precedent = 0
if (Test-Path $fiche) {
    try { $precedent = [int](Get-Content $fiche -Raw | ConvertFrom-Json).build } catch { $precedent = 0 }
}
$numero = [Math]::Max($precedent + 1, 1)
$commit = ''
if (Get-Command git -ErrorAction SilentlyContinue) { $commit = (& git -C $Racine rev-parse HEAD 2>$null) }

$mobile = Join-Path $Racine 'mobile'
Push-Location $mobile
try {
    Etape 'Dépendances (flutter pub get)…'
    & flutter pub get --enforce-lockfile
    if ($LASTEXITCODE -ne 0) { Write-Host 'flutter pub get a échoué (voir au-dessus).' -ForegroundColor Red; Fin 1 }
    Etape "Construction de l'APK (numéro $numero, plusieurs minutes)…"
    & flutter build apk --debug "--build-number=$numero" "--dart-define=LUDIFUN_BUILD=$numero"
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'La construction a échoué. Lance « flutter doctor » : il dit ce qui manque (SDK Android, licences…).' -ForegroundColor Red
        Fin 1
    }
} finally {
    Pop-Location
}

$apk = Join-Path $mobile 'build\app\outputs\flutter-apk\app-debug.apk'
if (-not (Test-Path $apk)) { Write-Host "APK introuvable : $apk" -ForegroundColor Red; Fin 1 }
Ok "APK construit : $apk"

if (-not $SansRanger) {
    New-Item -ItemType Directory -Force -Path $DossierTelephone | Out-Null
    Copy-Item $apk (Join-Path $DossierTelephone 'ludifun.apk') -Force
    # Même fiche que celle publiée par GitHub : le serveur la lit pour proposer la mise à jour.
    $json = @{ build = $numero; commit = "$commit".Trim() } | ConvertTo-Json -Compress
    [System.IO.File]::WriteAllText($fiche, $json, (New-Object System.Text.UTF8Encoding($false)))
    Ok "Rangé dans $DossierTelephone (ludifun.apk, construction $numero)"
    Write-Host '  Le téléphone le proposera à la prochaine ouverture de Ludifun, quand le serveur tourne.'
    Write-Host '  Sinon : copie ludifun.apk sur le téléphone puis ouvre-le.'
    Start-Process explorer.exe $DossierTelephone
}
Fin 0
