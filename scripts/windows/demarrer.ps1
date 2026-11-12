# Démarre Ludifun sur ce PC : Docker, choix de l'IA (première fois), serveur, puis l'adresse à
# saisir sur le téléphone.
. (Join-Path $PSScriptRoot 'commun.ps1')

Titre 'Démarrage de Ludifun'
Assurer-Docker
Assurer-Env
$reglages = Lire-Env
if ($reglages['LUDIFUN_AI_PROVIDER'] -eq 'ollama') {
    $modele = $reglages['LUDIFUN_AI_MODEL']
    if (-not $modele) { $modele = 'qwen2.5vl:7b' }
    Verifier-Ollama $modele (Adresse-Ollama $reglages)
}
Demarrer-Moteur-Images $reglages

# Une fois : proposer la recherche sur les sites éducatifs (explications et exercices sourcés).
$marqueRecherche = Join-Path $Racine '.ludifun-recherche'
if (-not (Recherche-Active $reglages) -and -not (Test-Path $marqueRecherche)) {
    Write-Host ''
    Write-Host 'Ludifun peut chercher sur des sites éducatifs de confiance (Vikidia, Lumni, Éduscol…) :'
    Write-Host 'explications avec leur source et questions d''entraînement en plus de la leçon.'
    Write-Host 'Seule la notion part sur Internet, jamais le prénom de l''enfant ni sa photo.'
    $oui = Read-Host 'L''activer sur ce PC ? (O/N, conseillé : O)'
    if ($oui -match '^[oOyY]') { Regler-Recherche $reglages $true; Ok 'Recherche activée'; $reglages = Lire-Env }
    Set-Content -Path $marqueRecherche -Value 'question posée'
}

Etape 'Démarrage du serveur (la première fois, ou après une mise à jour : plusieurs minutes)…'
Arreter-Anciennes-Copies
Sauvegarde-Automatique
& docker compose up -d --build
if ($LASTEXITCODE -ne 0) { Echec 'docker compose n''a pas pu démarrer le serveur (voir les messages au-dessus).' }
$sante = Attendre-Serveur
Ok 'Serveur prêt'
Afficher-IA $sante

$marque = Join-Path $Racine '.ludifun-demo'
if (-not (Test-Path $marque)) {
    Write-Host ''
    $demo = Read-Host 'Créer une famille de démonstration (Emma, 4 semaines de révisions) pour découvrir ? (O/N)'
    if ($demo -match '^[oOyY]') {
        & docker compose exec -T api python -m app.tools.demo_family --replace
        if ($LASTEXITCODE -eq 0) { Set-Content -Path $marque -Value 'démo créée' }
    } else {
        Set-Content -Path $marque -Value 'démo refusée'
    }
}

Afficher-Telephone
Write-Host ''
Write-Host 'Parent : crée ton compte dans l''appli (« Je suis un parent »), ou utilise la démo :'
Write-Host '         parent.demo@example.fr / demo-ludifun-2026'
Write-Host 'Enfant : dans l''espace parent, ouvre l''enfant → « Lier un appareil » pour avoir un code.'
Write-Host 'IA    : l''espace parent → Mon compte → « Intelligence artificielle » (Ollama conseillé).'
if (Recherche-Active (Lire-Env)) { Expliquer-Recherche }
Attendre-Fermeture
