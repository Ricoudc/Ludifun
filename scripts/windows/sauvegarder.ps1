# Sauvegarde les données de Ludifun (comptes, leçons, résultats des enfants) dans
# %LOCALAPPDATA%\Ludifun\sauvegardes. Les 14 plus récentes sont gardées. Démarrer-Ludifun en fait
# aussi une chaque jour, et toujours avant qu'une nouvelle version transforme la base.
. (Join-Path $PSScriptRoot 'commun.ps1')

Titre 'Sauvegarde de Ludifun'
Assurer-Docker
if (-not (Base-Existe)) { Ok 'Aucune donnée à sauvegarder pour l''instant (Ludifun n''a jamais démarré).'; Attendre-Fermeture; exit 0 }
Arreter-Anciennes-Copies
Etape 'Sauvegarde en cours…'
$fichier = Sauvegarder-Base 'manuelle'
if (-not $fichier) { Echec 'La sauvegarde n''a pas fonctionné (voir les messages au-dessus).' }
Ok "Sauvegarde faite : $fichier"
Write-Host ''
Write-Host 'Pour changer de PC ou garder une copie à l''abri, copie tout le dossier' -ForegroundColor Yellow
Write-Host "$(Split-Path $DossierSauvegardes) (sauvegardes et reglages.env) sur une clé USB." -ForegroundColor Yellow
Write-Host 'Sans reglages.env, les clés d''IA enregistrées par les familles seraient à recoller.'
Attendre-Fermeture
