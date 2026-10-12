# Essayer l'IA du PC sur ses vraies leçons (spécification technique §5.55), sans téléphone :
# une leçon par dossier dans eval\lessons (photos, PDF, Word ou LibreOffice). Pour chacune,
# eval\results\<date>\<leçon>.txt montre ce que Ludifun en fait : texte lu, notions et leur
# thème, jeux possibles, séance complète ; report.md résume. Rien n'est envoyé ailleurs que vers
# l'IA choisie (choix 4). Ces dossiers ne partent jamais sur GitHub (.gitignore).
. (Join-Path $PSScriptRoot 'commun.ps1')

Titre 'Essayer l''IA sur mes vraies leçons'
$Lecons = Join-Path $Racine 'eval\lessons'
$Resultats = Join-Path $Racine 'eval\results'
New-Item -ItemType Directory -Force -Path $Lecons, $Resultats | Out-Null
$dossiers = @(Get-ChildItem $Lecons -Directory)
if ($dossiers.Count -eq 0) {
    Write-Host 'Mets chaque leçon dans son propre dossier, par exemple :'
    Write-Host "  $Lecons\fractions\page1.jpg et page2.jpg   (photos, dans l'ordre des pages)"
    Write-Host "  $Lecons\revolution\lecon.pdf               (ou un Word .docx, un LibreOffice .odt)"
    Write-Host ''
    Write-Host 'Avant la photo, cache le nom de l''enfant et de l''école.' -ForegroundColor Yellow
    Write-Host 'Facultatif : un fichier expected.json par leçon pour mesurer la justesse (voir eval\README.md).'
    Write-Host 'Puis relance ce choix.'
    Start-Process explorer.exe $Lecons
    Attendre-Fermeture
    exit 0
}
Assurer-Docker
Etape "Analyse de $($dossiers.Count) leçon(s) avec l'IA du PC : compte une à deux minutes par leçon…"
& docker compose run --rm --no-deps -v "${Racine}\eval:/eval" api python -m app.tools.evaluate /eval/lessons --out /eval/results --concurrency 1
if ($LASTEXITCODE -ne 0) { Echec 'L''analyse n''a pas abouti (voir les messages au-dessus).' }
$dernier = Get-ChildItem $Resultats -Directory | Sort-Object Name | Select-Object -Last 1
if ($dernier) {
    Ok "Résultats : $($dernier.FullName)"
    Write-Host '  Ouvre les fichiers .txt (une leçon chacun) : notions, thème choisi par l''IA, jeux, séance.'
    Write-Host '  Si quelque chose ne va pas, envoie ces fichiers .txt (jamais les photos) pour l''améliorer.'
    Start-Process explorer.exe $dernier.FullName
}
Attendre-Fermeture
