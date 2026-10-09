# Rapport de diagnostic à coller dans la conversation avec Claude : état du serveur, appels à
# l'IA (durées, erreurs), Ollama et carte graphique. Ni prénom, ni texte de leçon, ni clé d'API.
. (Join-Path $PSScriptRoot 'commun.ps1')

Titre 'Rapport de diagnostic de Ludifun'
$lignes = New-Object System.Collections.Generic.List[string]
function Section([string]$titre) { $lignes.Add(''); $lignes.Add("##### $titre") }
function Ajouter($texte) { foreach ($l in ($texte | Out-String).TrimEnd() -split "`r?`n") { $lignes.Add($l) } }

$lignes.Add("Rapport Ludifun du $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")

Section 'Ordinateur'
try {
    $os = Get-CimInstance Win32_OperatingSystem
    Ajouter "$($os.Caption) · mémoire $([math]::Round($os.TotalVisibleMemorySize / 1MB)) Go"
    foreach ($carte in Get-CimInstance Win32_VideoController) { Ajouter "Carte graphique : $($carte.Name) (pilote $($carte.DriverVersion))" }
} catch { Ajouter 'inconnu' }

Section 'Réglages (.env, sans les clés)'
$reglages = Lire-Env
foreach ($cle in 'LUDIFUN_AI_PROVIDER', 'LUDIFUN_AI_MODEL', 'LUDIFUN_OLLAMA_BASE_URL', 'LUDIFUN_AI_BASE_URL', 'LUDIFUN_AI_DAILY_BUDGET_USD', 'LUDIFUN_OLLAMA_NUM_CTX', 'COMPOSE_PROFILES', 'LUDIFUN_WEB_SEARCH_URL', 'LUDIFUN_WEB_SOURCES', 'LUDIFUN_IMAGE_ENGINE', 'LUDIFUN_IMAGE_URL', 'LUDIFUN_IMAGE_DIR') {
    if ($reglages[$cle]) { Ajouter "$cle=$($reglages[$cle])" }
}

Section 'Version'
$installee = Version-Installee
Ajouter $(if ($installee) { "Ludifun $installee" } else { 'Ludifun : version inconnue (ZIP pas encore mis à jour par le menu)' })
Ajouter $(if (Installe-Avec-Git) { 'Mise à jour : git' } elseif (Test-Path $FichierJeton) { 'Mise à jour : ZIP, jeton GitHub enregistré' } else { 'Mise à jour : ZIP, pas de jeton GitHub' })

Section 'Docker'
if (Docker-Pret) { Ajouter (& docker compose ps -a 2>&1) } else { Ajouter 'Docker n''est pas lancé' }

Section 'Santé du serveur'
try { Ajouter ((Invoke-RestMethod -Uri $UrlSante -TimeoutSec 5) | ConvertTo-Json -Compress) } catch { Ajouter "injoignable : $($_.Exception.Message)" }

Section 'Appels à l''IA (page /suivi)'
try {
    $reponse = Invoke-WebRequest -Uri 'http://localhost:8000/suivi/rapport.txt' -UseBasicParsing -TimeoutSec 15
    Ajouter ([System.Text.Encoding]::UTF8.GetString($reponse.RawContentStream.ToArray()))
} catch { Ajouter "indisponible : $($_.Exception.Message)" }

Section 'Ollama'
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Ajouter (& ollama --version 2>&1)
    Ajouter 'Modèles chargés (PROCESSOR : GPU = carte graphique, CPU = processeur) :'
    Ajouter (& ollama ps 2>&1)
    Ajouter 'Modèles installés :'
    Ajouter (& ollama list 2>&1)
} else { Ajouter 'Ollama n''est pas installé sur ce PC' }
$reglages = Lire-Env
if ($reglages['LUDIFUN_AI_PROVIDER'] -eq 'ollama') {
    $modele = $reglages['LUDIFUN_AI_MODEL']
    if (-not $modele) { $modele = 'qwen2.5vl:7b' }
    $conseils = @(Conseils-Ollama $modele (Adresse-Ollama $reglages) $reglages)
    if ($conseils.Count -eq 0) { Ajouter "Vérification de « $modele » : lit les images, tient dans la carte graphique" }
    else { Ajouter 'À corriger :'; Ajouter ($conseils | ForEach-Object { "  - $_" }) }
}

Section 'Moteur d''images'
if ($reglages['LUDIFUN_IMAGE_ENGINE'] -eq 'sdcpp') {
    if (Moteur-Images-Repond) { Ajouter "répond sur le port $PortImages" } else { Ajouter 'ne répond pas' }
    foreach ($nom in 'moteur-images.log', 'moteur-images-erreurs.log') {
        $journal = Join-Path $reglages['LUDIFUN_IMAGE_DIR'] $nom
        if (Test-Path $journal) { Ajouter "$($nom) (fin) :"; Ajouter (Get-Content $journal -Tail 25 -Encoding UTF8) }
    }
} else { Ajouter "pas installé (facultatif : $(Choix 8))" }

Section 'Journal du serveur (IA et erreurs)'
if (Docker-Pret) {
    $journal = & docker compose logs api --tail 400 2>&1 | Select-String -Pattern 'IA :|Ollama :|ERROR|WARNING|Traceback|Error' | Select-Object -Last 60
    Ajouter ($journal | ForEach-Object { $_.Line })
}

$fichier = Join-Path $Racine 'rapport-ludifun.txt'
[System.IO.File]::WriteAllLines($fichier, [string[]]$lignes, (New-Object System.Text.UTF8Encoding($false)))
try { Set-Clipboard -Value ($lignes -join "`r`n") } catch { }
Ok "Rapport enregistré : $fichier"
Write-Host 'Il est aussi copié : colle-le (Ctrl+V) dans la conversation avec Claude.' -ForegroundColor Green
try { Start-Process notepad.exe $fichier } catch { }
Attendre-Fermeture
