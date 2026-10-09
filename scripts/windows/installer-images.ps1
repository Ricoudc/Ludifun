# Installe le moteur d'images de Ludifun (étape 27) sur ce PC : stable-diffusion.cpp (Vulkan :
# marche avec les cartes AMD, NVIDIA et Intel, sans kit à installer) et le modèle SDXL-Lightning.
# Tout reste sur ce PC ; les images attendent la validation du parent avant d'être montrées.
. (Join-Path $PSScriptRoot 'commun.ps1')

Titre 'Installation du moteur d''images de Ludifun'
Write-Host 'L''image de la leçon est facultative : sans ce moteur, Ludifun marche comme avant.'
Write-Host 'Il faut environ 8 Go d''espace disque (modèle de 7 Go) ; un SSD rend chaque image plus rapide.'
try {
    foreach ($carte in Get-CimInstance Win32_VideoController) { Write-Host "Carte graphique : $($carte.Name)" }
} catch { }
Write-Host ''

$reglages = Lire-Env
$defaut = $reglages['LUDIFUN_IMAGE_DIR']
if (-not $defaut) { $defaut = 'C:\Ludifun-Images' }
$dossier = (Read-Host "Dossier d'installation (Entrée = $defaut)").Trim()
if (-not $dossier) { $dossier = $defaut }
$modeles = Join-Path $dossier 'modeles'
$programme = Join-Path $dossier 'programme'
New-Item -ItemType Directory -Force -Path $modeles, $programme | Out-Null
if (-not (Test-Path $dossier)) { Echec "Impossible de créer le dossier $dossier." }

$lecteur = (Get-Item $dossier).PSDrive
$libre = [math]::Round($lecteur.Free / 1GB, 1)
if ($lecteur.Free -lt 8GB -and -not (Test-Path (Join-Path $modeles 'sdxl_lightning_4step.safetensors'))) {
    Echec "Il reste $libre Go sur le disque $($lecteur.Name): : il en faut 8. Choisis un autre dossier ou libère de la place."
}

# 1. Le programme : dernière version Windows Vulkan publiée sur GitHub.
if (Get-ChildItem $programme -Recurse -Filter 'sd-server.exe' -ErrorAction SilentlyContinue) {
    Ok 'Programme stable-diffusion.cpp déjà installé'
} else {
    Etape 'Recherche de la dernière version de stable-diffusion.cpp…'
    try {
        $version = Invoke-RestMethod -Uri 'https://api.github.com/repos/leejet/stable-diffusion.cpp/releases/latest' -TimeoutSec 30
    } catch { Echec "GitHub ne répond pas ($($_.Exception.Message)). Vérifie la connexion Internet." }
    $zip = $version.assets | Where-Object { $_.name -like '*bin-win-vulkan-x64.zip' } | Select-Object -First 1
    if (-not $zip) { Echec "Pas de version Windows Vulkan dans $($version.tag_name) : réessaie plus tard." }
    $fichierZip = Join-Path $dossier $zip.name
    Etape "Téléchargement de $($zip.name) ($([math]::Round($zip.size / 1MB)) Mo)…"
    & curl.exe -L --fail --retry 3 -o $fichierZip $zip.browser_download_url
    if ($LASTEXITCODE -ne 0) { Echec 'Le téléchargement du programme a échoué.' }
    Expand-Archive -Path $fichierZip -DestinationPath $programme -Force
    Remove-Item $fichierZip -ErrorAction SilentlyContinue
    if (-not (Get-ChildItem $programme -Recurse -Filter 'sd-server.exe')) { Echec 'sd-server.exe est absent de l''archive.' }
    Ok "Programme installé ($($version.tag_name))"
}

# 2. Les modèles (téléchargement repris là où il s'est arrêté si on relance le script).
$aTelecharger = @(
    @{ Nom = 'sdxl_lightning_4step.safetensors'; Url = 'https://huggingface.co/ByteDance/SDXL-Lightning/resolve/main/sdxl_lightning_4step.safetensors'; Min = 6GB; Libelle = 'modèle SDXL-Lightning (7 Go, le plus long)' },
    @{ Nom = 'sdxl_vae.safetensors'; Url = 'https://huggingface.co/madebyollin/sdxl-vae-fp16-fix/resolve/main/sdxl_vae.safetensors'; Min = 300MB; Libelle = 'décodeur d''images corrigé (330 Mo)' }
)
foreach ($m in $aTelecharger) {
    $chemin = Join-Path $modeles $m.Nom
    if ((Test-Path $chemin) -and (Get-Item $chemin).Length -ge $m.Min) { Ok "$($m.Nom) déjà téléchargé"; continue }
    Etape "Téléchargement du $($m.Libelle)…"
    & curl.exe -L --fail --retry 5 -C - -o $chemin $m.Url
    if ($LASTEXITCODE -ne 0 -or (Get-Item $chemin -ErrorAction SilentlyContinue).Length -lt $m.Min) {
        Echec "Le téléchargement de $($m.Nom) n'est pas allé au bout : relance ce script, il reprendra où il s'est arrêté."
    }
    Ok "$($m.Nom) téléchargé"
}

# 3. Les réglages de Ludifun (.env), puis le moteur et le serveur relancés.
$reglages = Lire-Env
$reglages['LUDIFUN_IMAGE_ENGINE'] = 'sdcpp'
$reglages['LUDIFUN_IMAGE_URL'] = "http://host.docker.internal:$PortImages"
$reglages['LUDIFUN_IMAGE_DIR'] = $dossier
Ecrire-Env $reglages
Ok 'Ludifun réglé pour dessiner les images'

Demarrer-Moteur-Images (Lire-Env)
if (Docker-Pret) {
    Etape 'Redémarrage du serveur avec ce réglage…'
    Arreter-Anciennes-Copies
    & docker compose up -d
    if ($LASTEXITCODE -eq 0) { Attendre-Serveur | Out-Null; Ok 'Serveur prêt' }
} else {
    Write-Host "Lance $(Choix 1) (démarrer) : le moteur d'images démarrera avec le serveur." -ForegroundColor Yellow
}
Write-Host ''
Write-Host 'Prochaine leçon analysée : une image sera proposée dans l''espace parent (écran des questions'
Write-Host 'de la leçon). Valide-la pour que l''enfant la voie, ou demande de la refaire.'
Write-Host 'Pour une leçon déjà analysée : bouton « Créer une image » sur ce même écran.'
Attendre-Fermeture
