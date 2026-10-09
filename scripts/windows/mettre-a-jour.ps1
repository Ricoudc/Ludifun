# Met Ludifun à jour tout seul : télécharge la dernière version depuis GitHub (git pull si le
# dossier vient de git, sinon l'archive ZIP), redémarre le serveur avec, puis récupère la
# nouvelle application du téléphone. Les réglages (.env), les données et les sauvegardes sont
# gardés.
. (Join-Path $PSScriptRoot 'commun.ps1')

Titre 'Mise à jour de Ludifun'
$ProgressPreference = 'SilentlyContinue'  # sinon Expand-Archive est très lent

# Fichiers de Ludifun retirés d'une version à l'autre, à effacer s'ils sont encore là (les
# anciens raccourcis avant Ludifun.bat).
$Anciens = @(
    'Activer-Recherche-Ludifun.bat', 'Arreter-Ludifun.bat', 'Changer-IA-Ludifun.bat',
    'Demarrer-Ludifun.bat', 'Installer-Images-Ludifun.bat', 'Mettre-a-jour-Ludifun.bat',
    'Rapport-Ludifun.bat', 'Restaurer-Ludifun.bat', 'Sauvegarder-Ludifun.bat',
    'Surveiller-Ludifun.bat', 'Voir-les-erreurs-Ludifun.bat'
)

# Copie la version téléchargée dans le dossier de Ludifun. Jamais .env ni les dossiers propres
# à ce PC ; un fichier retiré de Ludifun depuis la dernière mise à jour est effacé.
function Installer-Version([string]$source) {
    $nouveaux = @(Get-ChildItem $source -Recurse -File -Force |
        ForEach-Object { $_.FullName.Substring($source.Length).TrimStart('\', '/') })
    & robocopy $source $Racine /E /XF .env /NFL /NDL /NJH /NJS /NP /R:2 /W:2 | Out-Null
    if ($LASTEXITCODE -ge 8) { Echec 'Les nouveaux fichiers n''ont pas pu être copiés (un fichier ouvert ailleurs ?).' }
    $avant = if (Test-Path $ListeFichiers) { @(Get-Content $ListeFichiers -Encoding UTF8) } else { @() }
    foreach ($relatif in @($avant | Where-Object { $_ -and $nouveaux -notcontains $_ }) + $Anciens) {
        $chemin = Join-Path $Racine $relatif
        if ((Test-Path $chemin -PathType Leaf) -and $nouveaux -notcontains $relatif) {
            Remove-Item $chemin -Force -ErrorAction SilentlyContinue
        }
    }
    Set-Content -Path $ListeFichiers -Value $nouveaux -Encoding UTF8
}

function Mettre-A-Jour-Par-Zip($jeton, $derniere) {
    $temporaire = Join-Path $env:TEMP "ludifun-maj-$(Get-Random)"
    New-Item -ItemType Directory -Force -Path $temporaire | Out-Null
    try {
        Etape 'Téléchargement de la nouvelle version…'
        $archive = Join-Path $temporaire 'ludifun.zip'
        Telecharger-GitHub "$ApiGitHub/repos/$DepotGitHub/zipball/$($derniere.Sha)" 'application/vnd.github+json' $jeton $archive
        Etape 'Décompression…'
        $dossier = Join-Path $temporaire 'contenu'
        Expand-Archive -Path $archive -DestinationPath $dossier -Force
        # L'archive de GitHub contient un seul dossier (« Ricoudc-Ludifun-abc1234 »).
        $racineArchive = @(Get-ChildItem $dossier -Directory)[0].FullName
        if (-not (Test-Path (Join-Path $racineArchive 'docker-compose.yml'))) { Echec 'L''archive téléchargée est incomplète.' }
        Etape 'Installation des nouveaux fichiers (tes réglages et tes données sont gardés)…'
        Installer-Version $racineArchive
        Set-Content -Path $MarqueVersion -Value $derniere.Sha
        Ok 'Fichiers de Ludifun à jour.'
    } catch {
        Echec "La mise à jour n'a pas pu être téléchargée : $($_.Exception.Message)"
    } finally {
        Remove-Item $temporaire -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# Nouvel APK de test (publié par GitHub à chaque version, release « apk-test »), rangé dans le
# dossier « telephone » de Ludifun.
function Recuperer-Apk($jeton) {
    if ($jeton -eq $false) {
        Write-Host "Application du téléphone : https://github.com/$DepotGitHub/releases/tag/apk-test" -ForegroundColor Yellow
        return
    }
    try {
        $release = Api-GitHub '/releases/tags/apk-test' $jeton
        $apk = if ($release) { @($release.assets | Where-Object { $_.name -like '*.apk' })[0] } else { $null }
        if (-not $apk) { Write-Host 'Pas encore d''application de test publiée sur GitHub.' -ForegroundColor Yellow; return }
        $connue = if (Test-Path $MarqueApk) { (Get-Content $MarqueApk -Raw).Trim() } else { '' }
        $fichier = Join-Path $DossierTelephone 'ludifun.apk'
        if ($connue -eq $apk.updated_at -and (Test-Path $fichier)) { Ok 'L''application du téléphone est déjà la dernière.'; return }
        Etape 'Téléchargement de la nouvelle application du téléphone…'
        New-Item -ItemType Directory -Force -Path $DossierTelephone | Out-Null
        Telecharger-GitHub $apk.url 'application/octet-stream' $jeton $fichier
        Set-Content -Path $MarqueApk -Value $apk.updated_at
        Ok "Nouvelle application du téléphone : $fichier"
        Write-Host '  À installer sur le téléphone : copie ludifun.apk (câble USB, Google Drive, e-mail…) puis ouvre-le.'
        Write-Host '  Tes réglages et ton compte restent dans l''application.'
        Start-Process explorer.exe $DossierTelephone
    } catch {
        Write-Host "L'application du téléphone n'a pas pu être téléchargée : $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

$jeton = $false
if (Installe-Avec-Git) {
    Etape 'Téléchargement des nouveautés (git)…'
    & git -C $Racine pull
    if ($LASTEXITCODE -ne 0) { Echec 'git pull n''a pas fonctionné (voir les messages au-dessus).' }
    try { $jeton = Acces-GitHub $false } catch { $jeton = $false }
} else {
    Etape 'Recherche de la dernière version sur GitHub…'
    try { $jeton = Acces-GitHub } catch { Echec "GitHub ne répond pas (Internet coupé ?) : $($_.Exception.Message)" }
    if ($jeton -eq $false) { Echec 'Sans jeton GitHub, la mise à jour ne peut pas télécharger Ludifun.' }
    $derniere = Derniere-Version $jeton
    if (-not $derniere) { Echec 'GitHub n''a pas donné la dernière version.' }
    if ($derniere.Sha -eq (Version-Installee)) {
        Ok 'Ludifun est déjà à jour.'
    } else {
        Mettre-A-Jour-Par-Zip $jeton $derniere
    }
}

Assurer-Docker
Assurer-Env
Arreter-Anciennes-Copies
Sauvegarde-Automatique
Etape 'Reconstruction et redémarrage du serveur (quelques minutes)…'
& docker compose up -d --build
if ($LASTEXITCODE -ne 0) { Echec 'docker compose n''a pas pu redémarrer le serveur.' }
Afficher-IA (Attendre-Serveur)
Recuperer-Apk $jeton
Attendre-Fermeture
