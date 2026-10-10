# Change l'IA utilisée (celle qui lit les photos et crée les jeux, puis celle qui dessine les
# images : sur ce PC ou en ligne avec Pollinations) puis redémarre le serveur.
. (Join-Path $PSScriptRoot 'commun.ps1')

Titre 'Choix de l''IA de Ludifun'
Choisir-IA
Assurer-Docker
Arreter-Anciennes-Copies
Demarrer-Moteur-Images (Lire-Env)  # images sur ce PC : le moteur doit tourner
Etape 'Redémarrage du serveur avec ce réglage…'
& docker compose up -d
if ($LASTEXITCODE -ne 0) { Echec 'Le redémarrage n''a pas fonctionné.' }
Afficher-IA (Attendre-Serveur)
Attendre-Fermeture
