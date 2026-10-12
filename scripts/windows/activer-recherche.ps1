# Active (ou désactive) la recherche sur les sites éducatifs de confiance (étapes 24 et 29) : le
# moteur SearXNG dans Docker, puis le serveur redémarré. Chaque parent l'autorise ensuite dans
# l'application.
. (Join-Path $PSScriptRoot 'commun.ps1')

Titre 'Recherche sur les sites éducatifs'
Assurer-Docker
Assurer-Env
$reglages = Lire-Env
if (Recherche-Active $reglages) {
    Ok 'La recherche est déjà activée sur ce PC.'
    $non = Read-Host 'La désactiver ? (O/N)'
    if ($non -match '^[oOyY]') {
        & docker compose --profile recherche stop recherche *> $null
        Regler-Recherche $reglages $false
        Ok 'Recherche désactivée'
    }
} else {
    Write-Host 'Ludifun cherchera sur Vikidia, Lumni, Éduscol, Sésamath et Wikipédia : explications avec'
    Write-Host 'leur source (« Je n''ai pas compris ») et questions d''entraînement en plus de la leçon.'
    Write-Host 'Seule la notion part sur Internet, jamais le prénom de l''enfant ni sa photo.'
    Regler-Recherche $reglages $true
    Ok 'Recherche activée'
}
Set-Content -Path (Join-Path $Racine '.ludifun-recherche') -Value 'réglée'

Etape 'Redémarrage du serveur (la première fois : téléchargement du moteur de recherche)…'
Arreter-Anciennes-Copies
& docker compose up -d --remove-orphans
if ($LASTEXITCODE -ne 0) { Echec 'Le redémarrage n''a pas fonctionné (voir les messages au-dessus).' }
Attendre-Serveur | Out-Null
Ok 'Serveur prêt'
if (Recherche-Active (Lire-Env)) {
    Expliquer-Recherche
    Write-Host 'Les leçons déjà analysées n''en profitent pas : elles gardent leurs questions.' -ForegroundColor Yellow
}
Attendre-Fermeture
